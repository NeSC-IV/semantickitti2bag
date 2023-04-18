from rclpy.clock import Clock
from rclpy.duration import Duration
from rclpy.serialization import serialize_message
from example_interfaces.msg import Int32
import rclpy
from rclpy.time import Time

import rosbag2_py
import sys
sys.dont_write_bytecode = True
import math
import utils #import utils.py
from numpy.linalg import inv
import tf_transformations
import os
import cv2
# from cv_bridge import CvBridge
import progressbar
from tf2_msgs.msg import TFMessage
from datetime import datetime
from std_msgs.msg import Header
from sensor_msgs.msg import CameraInfo, Imu, PointField, NavSatFix
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2 as pcl2 # point_cloud2.create_cloud() 函数是sensor_msgs.msg.PointCloud2消息的一个帮助函数，它将一系列点的x、y、z坐标和其他属性打包到点云消息中。
from geometry_msgs.msg import TransformStamped, TwistStamped, Transform, PoseStamped
from nav_msgs.msg import Odometry
import numpy as np
import argparse
import glob



class SemanticKitti_Raw:
    """Load and parse raw data into a usable format"""

    def __init__(self, dataset_path, sequence_number, scanlabel_bool, **kwargs):
        self.data_path = os.path.join(dataset_path, 'sequences', sequence_number)

        self.frames = kwargs.get('frames', None)

        self.imtype = kwargs.get('imtype', 'png')

        self._get_file_lists(scanlabel_bool)
        #self._load_calib()
        
        self._load_timestamps()

    def _get_file_lists(self, scanlabel_bool):
        # self.cam0_files = sorted(glob.glob(
        #     os.path.join(self.data_path, 'image_0', '*.{}'.format(self.imtype))))

        # self.cam1_files = sorted(glob.glob(
        #     os.path.join(self.data_path, 'image_1', '*.{}'.format(self.imtype))))
        
        # self.cam2_files = sorted(glob.glob(
        #     os.path.join(self.data_path, 'image_2', '*.{}'.format(self.imtype))))       
        
        # self.cam3_files = sorted(glob.glob(
        #     os.path.join(self.data_path, 'image_3', '*.{}'.format(self.imtype))))

        self.velo_files = sorted(glob.glob(
            os.path.join(self.data_path, 'velodyne', '*.bin')))

        if scanlabel_bool == 1:
            self.label_files = sorted(glob.glob(
                os.path.join(self.data_path, 'labels', '*.label')))
        #print(self.cam1_files)
        #print(self.velo_files)

        # if self.frames is not None:

    def _load_timestamps(self):
        timestamp_file = os.path.join(
                self.data_path, 'times.txt')

        self.timestamps = []
        with open(timestamp_file, 'r') as f:
            for line in f.readlines():
                #number = datetime.fromtimestamp(float(line))
                number = float(line)
                if number == 0.0:
                    number = 0.0001
                #sign = 1.0
                
                #if line[9]=='+':
                #    sign = 1.0
                #else:
                #    sign = -1.0

                #num = float(line[10])*10 + float(line[11])*1

                #time_t = number*(10**(sign*num))
                #print(line)
                #print(type(line))
                #print(number)
                #print(type(number))
                self.timestamps.append(number)

def inv_t(transform):

    R = transform[0:3, 0:3]
    t = transform[0:3, 3]
    t_inv = -1*R.T.dot(t)
    transform_inv = np.eye(4)
    transform_inv[0:3, 0:3] = R.T
    transform_inv[0:3, 3] = t_inv

    return transform_inv

def save_velo_data_with_label(writer, kitti, velo_frame_id, velo_topic):
    print("Exporting Velodyne and Label data")
    topic_info = rosbag2_py._storage.TopicMetadata(
        name=velo_topic,
        type='sensor_msgs/PointCloud2',
        serialization_format='cdr') # 默认二进制序列化格式
    
    writer.create_topic(topic_info)

    velo_data_dir = os.path.join(kitti.data_path, 'velodyne')
    velo_filenames = sorted(os.listdir(velo_data_dir))

    label_data_dir = os.path.join(kitti.data_path, 'labels')
    label_filenames = sorted(os.listdir(label_data_dir))

    datatimes = kitti.timestamps

    iterable = zip(datatimes, velo_filenames, label_filenames)
    bar = progressbar.ProgressBar()

    for dt, veloname, labelname in bar(list(iterable)):
        if dt is None:
            continue

        velo_filename = os.path.join(velo_data_dir, veloname)
        label_filename = os.path.join(label_data_dir, labelname)

        veloscan = (np.fromfile(velo_filename, dtype=np.float32)).reshape(-1, 4)
        labelscan = (np.fromfile(label_filename, dtype=np.int32)).reshape(-1,1)
        
        labeldata = utils.LabelDataConverter(labelscan)
        
        scan = []

        for t in range(len(labeldata.rgb_id)):
            point = [veloscan[t][0], veloscan[t][1], veloscan[t][2], veloscan[t][3], labeldata.rgb_id[t], labeldata.semantic_id[t]]
            scan.append(point)

        header = Header()
        header.frame_id = velo_frame_id
        time = Time(seconds = float(dt)) # Clock().now()
        header.stamp = time.to_msg()

        fields =[PointField(name='x',  offset=0, datatype=PointField.FLOAT32, count = 1),
                PointField(name='y',  offset=4, datatype=PointField.FLOAT32, count = 1),
                PointField(name='z',  offset=8, datatype=PointField.FLOAT32, count = 1),
                PointField(name='intensity',  offset=12, datatype=PointField.FLOAT32, count = 1),
                PointField(name='rgb',  offset=16, datatype=PointField.UINT32, count = 1),
                PointField(name='label',  offset=20, datatype=PointField.UINT16, count = 1)]

        pcl_msg = pcl2.create_cloud(header, fields, scan)
        writer.write(
            velo_topic,
            serialize_message(pcl_msg),
            time.nanoseconds)
        # bag.write(velo_topic, pcl_msg, t=pcl_msg.header.stamp)

def save_velo_data(writer, kitti, velo_frame_id, velo_topic):
    print("Exporting Velodyne data")
    topic_info = rosbag2_py._storage.TopicMetadata(
        name=velo_topic,
        type='sensor_msgs/PointCloud2',
        serialization_format='cdr') # 默认二进制序列化格式
    
    writer.create_topic(topic_info)
    velo_data_dir = os.path.join(kitti.data_path, 'velodyne')
    velo_filenames = sorted(os.listdir(velo_data_dir))

    datatimes = kitti.timestamps

    iterable = zip(datatimes, velo_filenames)
    bar = progressbar.ProgressBar()

    for dt, veloname in bar(list(iterable)):
        if dt is None:
            continue

        velo_filename = os.path.join(velo_data_dir, veloname)

        veloscan = (np.fromfile(velo_filename, dtype=np.float32)).reshape(-1, 4)

        header = Header()
        header.frame_id = velo_frame_id
        time = Time(seconds = float(dt)) # Clock().now()
        header.stamp = time.to_msg()

        fields =[PointField(name='x',  offset=0, datatype=PointField.FLOAT32, count = 1),
                PointField(name='y',  offset=4, datatype=PointField.FLOAT32, count = 1),
                PointField(name='z',  offset=8, datatype=PointField.FLOAT32, count = 1),
                PointField(name='intensity',  offset=12, datatype=PointField.FLOAT32, count = 1)]

        pcl_msg = pcl2.create_cloud(header, fields, veloscan)
        writer.write(
            velo_topic,
            serialize_message(pcl_msg),
            time.nanoseconds)
        # bag.write(velo_topic, pcl_msg, t=pcl_msg.header.stamp)

def read_calib_file(filename):
    """ read calibration file 

        returns -> dict calibration matrices as 4*4 numpy arrays
    """
    calib = {}
    """calib1 = np.eye(4,4)
    calib1[0:3, 3] = [0.27, 0.0, -0.08]
    print(calib1)
    calib.append(calib1)

    calib2 = np.eye(4,4)
    calib2[0:3, 3] = [0.27, -0.51, -0.08]
    print(calib2)
    calib.append(calib2)

    calib3 = np.eye(4,4)
    calib3[0:3, 3] = [0.27, 0.06, -0.08]
    print(calib3)
    calib.append(calib3)

    calib4 = np.eye(4,4)
    calib4[0:3, 3] = [0.27, -0.45, -0.08]
    print(calib4)
    calib.append(calib4)"""
    calib_file = open(filename)

    key_num = 0

    for line in calib_file:
        key, content = line.strip().split(":")
        values = [float(v) for v in content.strip().split()]
        pose = np.zeros((4,4))
        
        pose[0, 0:4] = values[0:4]
        pose[1, 0:4] = values[4:8]
        pose[2, 0:4] = values[8:12]
        pose[3, 3] = 1.0

        calib[key] = pose

    calib_file.close()
    
    #print(calib)
    return calib

def read_poses_file(filename, calibration):
    pose_file = open(filename)

    poses = []

    Tr = calibration["Tr"]
    Tr_inv = inv(Tr)

    for line in pose_file:
        values = [float(v) for v in line.strip().split()]

        pose = np.zeros((4, 4))
        pose[0, 0:4] = values[0:4]
        pose[1, 0:4] = values[4:8]
        pose[2, 0:4] = values[8:12]
        pose[3, 3] = 1.0

        poses.append(np.matmul(Tr_inv, np.matmul(pose, Tr)))
        #poses.append(pose)

    pose_file.close()
    return poses

def get_static_transform(from_frame_id, to_frame_id, transform):
    t = transform[0:3, 3] #Get translation vector
    q = tf_transformations.quaternion_from_matrix(transform) #Create quaternion from 4*4 homogenerous transformation matrix
    q_n = q / np.linalg.norm(q) #(x,y,z,w)

    tf_msg = TransformStamped()
    tf_msg.header.frame_id = from_frame_id #master
    tf_msg.child_frame_id = to_frame_id
    tf_msg.transform.translation.x = t[0]
    tf_msg.transform.translation.y = t[1]
    tf_msg.transform.translation.z = t[2]
    tf_msg.transform.rotation.x = q_n[0]
    tf_msg.transform.rotation.y = q_n[1]
    tf_msg.transform.rotation.z = q_n[2]
    tf_msg.transform.rotation.w = q_n[3]

    return tf_msg

def save_static_transforms(writer, transforms, kitti):
    print("Get static transform")
    # 将tf message通过writer写入rosbag2

    topic_info = rosbag2_py._storage.TopicMetadata(
        name='/tf_static',
        type='tf2_msgs/TFMessage',
        serialization_format='cdr') # 默认二进制序列化格式
    
    writer.create_topic(topic_info)
    tfm = TFMessage()
    datatimes = kitti.timestamps

    for transform in transforms:
        at = get_static_transform(transform[0], transform[1], transform[2])
        #print(at)
        tfm.transforms.append(at)

    for dt in datatimes:
        #time = rospy.Time.from_sec(float(dt.strftime("%s.%f")))
        time = Time(seconds = float(dt)) # Clock().now()
        #print(dt)
        #print(type(time))
        for i in range(len(tfm.transforms)):
            tfm.transforms[i].header.stamp = time.to_msg()
            # tfm.transforms[i].header.stamp = time
        # bag.write('/tf_static', tfm, t=time)
        writer.write(
            '/tf_static',
            serialize_message(tfm),
            time.nanoseconds)


def save_dynamic_transforms(writer, kitti, poses, master_frame_id, slave_frame_id,initial_time):
    print("Exporting time dependent transformations")
    topic_info = rosbag2_py._storage.TopicMetadata(
        name='/tf',
        type='tf2_msgs/TFMessage',
        serialization_format='cdr') # 默认二进制序列化格式
    
    writer.create_topic(topic_info)

    datatimes = kitti.timestamps
    iterable = zip(datatimes, poses)
    bar = progressbar.ProgressBar()
    for dt, pose in bar(list(iterable)):
        tf_dy_msg = TFMessage()
        tf_dy_transform = TransformStamped()
        
        #tf_dy_transform.header.stamp = rospy.Time.from_sec(float(dt.strftime("%s.%f")))
        time = Time(seconds = float(dt))
        tf_dy_transform.header.stamp = time.to_msg()
        #print(tf_dy_transform.header.stamp)

        tf_dy_transform.header.frame_id = master_frame_id
        tf_dy_transform.child_frame_id = slave_frame_id

        t = pose[0:3, 3]
        q = tf_transformations.quaternion_from_matrix(pose)

        dy_tf = Transform()

        dy_tf.translation.x = t[0]
        dy_tf.translation.y = t[1]
        dy_tf.translation.z = t[2]

        q_n = q / np.linalg.norm(q)

        dy_tf.rotation.x = q_n[0]
        dy_tf.rotation.y = q_n[1]
        dy_tf.rotation.z = q_n[2]
        dy_tf.rotation.w = q_n[3]

        tf_dy_transform.transform = dy_tf
        tf_dy_msg.transforms.append(tf_dy_transform)
        writer.write(
            '/tf',
            serialize_message(tf_dy_msg),
            time.nanoseconds)

# def save_camera_data(bag, kitti, calibration, bridge, camera, camera_frame_id, topic, initial_time):
#     print("Exporting {} image data".format(topic))
#     datatimes = kitti.timestamps

#     image_file_dir = os.path.join(kitti.data_path, 'image_{}'.format(camera))
#     image_file_names = sorted(os.listdir(image_file_dir))

#     calib = CameraInfo()
#     calib.header.frame_id = camera_frame_id
#     #P = calibration["{}".format(camera)]
#     #calib.P


#     iterable = zip(datatimes, image_file_names)
#     bar = progressbar.ProgressBar()

#     for dt, filename in bar(iterable):
#         image_filename = os.path.join(image_file_dir, filename)
#         cv_image = cv2.imread(image_filename)
#         #calib.height, calib.width = cv_image.shape[ :2]

#         if camera in (0, 1):
#             #image_0 and image_1 contain monocolor image, but these images are represented as RGB color
#             cv_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

#         encoding = "mono8" if camera in (0, 1) else "bgr8"
#         image_message = bridge.cv2_to_imgmsg(cv_image, encoding=encoding)
#         image_message.header.frame_id = camera_frame_id
#         image_message.header.stamp = rospy.Time.from_sec(float(dt))
#         topic_ext = "/image_raw"

#         #calib.header.stamp = image_message.header.stamp

#         bag.write(topic + topic_ext, image_message, t=image_message.header.stamp)
#         #bag.write(topic + '/camera_info', calib, t=calib.header.stamp)


def save_pose_msg(writer, kitti, poses, master_frame_id, slave_frame_id, topic, initial_time=None):
    print("Exporting pose msg")
    # odom_pose存储位姿信息和速度信息
    topic_info = rosbag2_py._storage.TopicMetadata(
        name='/odom_pose',
        type='nav_msgs/Odometry',
        serialization_format='cdr') # 默认二进制序列化格式
    
    writer.create_topic(topic_info)
    # posestamp只存储位姿信息
    topic_info2 = rosbag2_py._storage.TopicMetadata(
        name=topic,
        type='geometry_msgs/PoseStamped',
        serialization_format='cdr') # 默认二进制序列化格式
    
    writer.create_topic(topic_info2)
    datatimes = kitti.timestamps

    iterable = zip(datatimes, poses)
    bar = progressbar.ProgressBar()

    p_t1 = PoseStamped()
    dt_1 = 0.00
    counter = 0

    for dt, pose in bar(list(iterable)):
        p = PoseStamped()
        p.header.frame_id = master_frame_id
        time = Time(seconds = float(dt))
        p.header.stamp = time.to_msg()

        t = pose[0:3, 3]
        q = tf_transformations.quaternion_from_matrix(pose)

        p.pose.position.x = t[0]
        p.pose.position.y = t[1]
        p.pose.position.z = t[2]

        q_n = q / np.linalg.norm(q)

        p.pose.orientation.x = q_n[0]
        p.pose.orientation.y = q_n[1]
        p.pose.orientation.z = q_n[2]
        p.pose.orientation.w = q_n[3]

        if(counter == 0):
            p_t1 = p

        writer.write(
            topic,
            serialize_message(p),
            time.nanoseconds)
        # bag.write(topic, p, t=p.header.stamp)

        delta_t = (dt - dt_1)
        if(counter == 0):
            delta_t = 0.00000001
        
        vx = (p.pose.position.x - p_t1.pose.position.x )/delta_t
        vy = (p.pose.position.y - p_t1.pose.position.y )/delta_t
        vz = (p.pose.position.z - p_t1.pose.position.z )/delta_t

        vqx = (p.pose.orientation.x - p_t1.pose.orientation.x)
        vqy = (p.pose.orientation.y - p_t1.pose.orientation.y)
        vqz = (p.pose.orientation.z - p_t1.pose.orientation.z)
        vqw = (p.pose.orientation.w - p_t1.pose.orientation.w)
  
        v_roll = math.atan2( 2*(vqw*vqx + vqy*vqz), 1-2*(vqx**2 + vqy**2)  )/delta_t
        v_pitch = math.asin( 2*(vqw*vqy - vqz*vqx) )/delta_t
        v_yaw = math.atan2( 2*(vqw*vqz + vqx*vqy) , 1-2*(vqy**2 + vqz**2)  )/delta_t

        odom = Odometry()
        odom.header.stamp = p.header.stamp
        odom.header.frame_id = master_frame_id
        odom.child_frame_id = slave_frame_id

        odom.pose.pose.position = p.pose.position
        odom.pose.pose.orientation = p.pose.orientation
        
        odom.twist.twist.linear.x = vx
        odom.twist.twist.linear.y = vy
        odom.twist.twist.linear.z = vz
        
        
        odom.twist.twist.angular.x = v_roll
        odom.twist.twist.angular.y = v_pitch
        odom.twist.twist.angular.z = v_yaw
        writer.write(
            '/odom_pose',
            serialize_message(odom),
            time.nanoseconds)
        # bag.write('/odom_pose', odom, t=odom.header.stamp)
        
        counter += 1
        p_t1 = p
        dt_1 = dt

def main(args=None):
    writer = rosbag2_py.SequentialWriter()
    sequence_number = "00" # 00~21
    storage_options = rosbag2_py._storage.StorageOptions(
        uri="bags/semantickitti_sequence{}".format(sequence_number),
        storage_id='sqlite3') 
    converter_options = rosbag2_py._storage.ConverterOptions('', '')
    writer.open(storage_options, converter_options)

    # topic_info = rosbag2_py._storage.TopicMetadata(
    #     name='synthetic',
    #     type='example_interfaces/msg/Int32',
    #     serialization_format='cdr')
    # writer.create_topic(topic_info)

    # time_stamp = Clock().now()
    # for ii in range(0, 100):
    #     data = Int32()
    #     data.data = ii
    #     writer.write(
    #         'synthetic',
    #         serialize_message(data),
    #         time_stamp.nanoseconds)
    #     time_stamp += Duration(seconds=1)
    # parser = argparse.ArgumentParser(description='Convert SemanticKITTI dataset to rosbag file')


    # parser.add_argument("-p","--dataset_path", help='Path to Semantickitti file')
    # parser.add_argument("-s","--sequence_number", help='Sequence number, must be written as 1 to 01')
    # args = parser.parse_args()

    # bridge = CvBridge()
    # compression = rosbag.Compression.NONE

    #camera

    # cameras = [
    #         (0, 'camera_gray_left', '/semantickitti/camera_gray_left'),
    #         (1, 'camera_gray_right', '/semantickitti/camera_gray_right'),
    #         (2, 'camera_color_left', '/semantickitti/camera_color_left'),
    #         (3, 'camera_color_right', '/semantickitti/camera_color_right')
    #     ]
    
    # if args.dataset_path == None:
    #     print("Dataset path is not given.")
    #     sys.exit(1)
    # elif args.sequence_number == None:
    #     print("Sequence number is not given.")
    #     sys.exit(1)

    scanlabel_bool = 1
    if int(sequence_number) > 10:
        scanlabel_bool = 0
        
    # bag = rosbag.Bag("semantickitti_sequence{}.bag".format(args.sequence_number), 'w', compression=compression)

    kitti = SemanticKitti_Raw("/media/oliver/Elements SE/dataset/KITTI", sequence_number, scanlabel_bool)

    if not os.path.exists(kitti.data_path):
        print('Path {} does not exists. Force-quiting....'.format(kitti.data_path))
        sys.exit(1)

    if len(kitti.timestamps) == 0:
        print('Dataset is empty? Check your semantickitti dataset file')
        sys.exit(1)
    
    try:
        world_frame_id = 'map'

        vehicle_frame_id = 'vehicle'
        vehicle_topic = '/vehicle'

        ground_truth_frame_id = 'ground_truth'
        ground_truth_topic = '/ground_truth'

        velo_frame_id = 'velodyne'
        velo_topic = '/velodyne_points'

        vehicle_frame_id = vehicle_frame_id

        T_base_link_to_velo = np.eye(4, 4)

        calibration = read_calib_file(os.path.join(kitti.data_path, 'calib.txt'))
        
        calib0 = np.eye(4,4)
        calib0[0:3, 3] = [0.27, 0.0, -0.08]
        #print(calib0)
        
        calib1 = np.eye(4,4)
        calib1[0:3, 3] = [0.27, -0.51, -0.08]
        #print(calib1)
        
        calib2 = np.eye(4,4)
        calib2[0:3, 3] = [0.27, 0.06, -0.08]
        #print(calib2)
        
        calib3 = np.eye(4,4)
        calib3[0:3, 3] = [0.27, -0.45, -0.08]
        #print(calib3)
        
        #tf-static

        transforms = [
            (vehicle_frame_id, velo_frame_id, T_base_link_to_velo) #,
            # (vehicle_frame_id, cameras[0][1], calib0),
            # (vehicle_frame_id, cameras[1][1], calib1),
            # (vehicle_frame_id, cameras[2][1], calib2),
            # (vehicle_frame_id, cameras[3][1], calib3)
        ]


        save_static_transforms(writer, transforms, kitti) # velodyne to vehicle/groundtruth

        #These poses are represented in world coordinate
        # poses = read_poses_file(os.path.join(kitti.data_path,'poses.txt'), calibration) # poses.txt由suma生成
        
        ground_truth_file_name = "{}.txt".format(sequence_number)
        ground_truth = read_poses_file(os.path.join(kitti.data_path, ground_truth_file_name), calibration)

        # save_dynamic_transforms(writer, kitti, poses, world_frame_id, vehicle_frame_id, initial_time=None) # tf vehicle to map
        save_dynamic_transforms(writer, kitti, ground_truth, world_frame_id, ground_truth_frame_id, initial_time=None) # tf ground_truth to map

        # save_pose_msg(writer, kitti, poses, world_frame_id, vehicle_frame_id, vehicle_topic, initial_time=None)
        save_pose_msg(writer, kitti, ground_truth, world_frame_id, ground_truth_frame_id, ground_truth_topic, initial_time=None) # posestamped: ground_truth to map, odom: ground_truth to map

        
        if scanlabel_bool == 1:
            #print('a')
            save_velo_data_with_label(writer, kitti, velo_frame_id, velo_topic)
            #save_velo_data(bag, kitti, velo_frame_id, velo_topic)

        elif scanlabel_bool == 0:
            #print('b')
            save_velo_data(writer, kitti, velo_frame_id, velo_topic)

        # for camera in cameras:
        #     #print('c')
        #     save_camera_data(bag, kitti, calibration, bridge, camera=camera[0], camera_frame_id=camera[1], topic=camera[2], initial_time=None)


    finally:
        print('Convertion is done')
        # print(bag)
        # bag.close()
if __name__ == '__main__':
    main()