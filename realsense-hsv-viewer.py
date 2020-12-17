## License: Apache 2.0. See LICENSE file in root directory.
## Copyright(c) 2015-2017 Intel Corporation. All Rights Reserved.

###############################################
##      Open CV and Numpy integration        ##
###############################################
try:
        import pyrealsense2.pyrealsense2 as rs
except ModuleNotFoundError:
        print('Use local realsense lib')
        import pyrealsense2 as rs

import numpy as np
import cv2
from timeit import default_timer as timer

# Configure depth and color streams
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

colorizer = rs.colorizer()
colorizer.set_option(rs.option.color_scheme, 0)


# Start streaming
pipeline.start(config)

align_to = rs.stream.depth
align = rs.align(align_to)

try:
    while True:
        start = timer()
        # Wait for a coherent pair of frames: depth and color
        frames = pipeline.wait_for_frames()
        #frameWait = timer ()
        #frameWaitTime = frameWait - start
        #print(str(frameWaitTime) + " frame wait time")
        # Align the depth frame to color frame
        aligned_frames = align.process(frames)

        depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()
        if not depth_frame or not color_frame:
            continue

        #syncedFrame = timer()
        #syncedFrameTime = syncedFrame - start
        #print(str(syncedFrameTime) + " synced time")

        # Convert images to numpy arrays
        #depth_image = np.asanyarray(depth_frame.get_data())
        depth_image = np.asanyarray(colorizer.colorize(depth_frame).get_data()) #intel realsense colorizer
        color_image = np.asanyarray(color_frame.get_data())
        #frameToNp = timer()
        #frameToNpTime = frameToNp - start
        #print(str(frameToNpTime) + " numpy array time")

        # We need to encode/pack the 16bit depth value to RGB
        # we do this by treating it as the Hue in HSV. 
        # we then encode HSV to RGB and stream that
        # on the other end we reverse RGB to HSV, H will give us the depth value back.
        # HSV elements are in the 0-1 range so we need to normalize the depth array to 0-1
        # First set a far plane and set everything beyond that to 0
        
        #start = timer()
        clipped = depth_image > 4000
        depth_image[clipped] = 0
        #hsvTimer = timer()
        #print(str(hsvTimer - start) + " clip")

        # Now normalize using that far plane
        # cv expects the H in degrees, not 0-1 :(
        #start = timer()
        #depth_image_norm = (depth_image * (360/4000)).astype( np.float32)
        #hsvTimer = timer()
        #print(str(hsvTimer - start) + " depth_image_norm")

        # Create 3 dimensional HSV array where H=depth, S=1, V=1
        #start = timer()
        #depth_hsv = np.concatenate([depth_image_norm[..., np.newaxis]]*3, axis=2)
        #depth_hsv[:,:,0:2] = 1
        #depth_hsv[:,:,1] = 1
        #depth_hsv[:,:,2] = 1
        #hsvTimer = timer()
        #print(str(hsvTimer - start) + " depth_concat")


        #start = timer()
        #discard = depth_image_norm == 0
        #s = depth_hsv[:,:,1]
        #v = depth_hsv[:,:,2] 
        #s[ discard] = 0
        #v[ discard] = 0
        #hsvTimer = timer()
        #print(str(hsvTimer - start) + " s v discard")

        # cv2.cvtColor to convert HSV to RGB
        # problem is that cv2 expects hsv to 8bit (0-255)
        #start = timer()
        #hsv = cv2.cvtColor(depth_hsv, cv2.COLOR_HSV2BGR)
        #hsvTime = timer()
        #print(str(hsvTime-start) + " hsv conversion time")

        # Stack both images horizontally
        #start = timer()
        color32 = (color_image/256).astype( np.float32)
        images = np.vstack((color32, depth_image)) # intel hsv
        #images = np.vstack((color32, hsv))


        # ffplay -f avfoundation -i "2:0" -vf  "crop=1024:768:400:800" -pix_fmt yuv420p -y 
        
        # Show images
        cv2.namedWindow('RealSense', cv2.WINDOW_AUTOSIZE)
        cv2.moveWindow("RealSense", 0,0)
        cv2.imshow('RealSense', images)
        cv2.waitKey(1)
        windowTime = timer()
        print(str(windowTime-start) + " opencv window time")

finally:

    # Stop streaming
    pipeline.stop()
