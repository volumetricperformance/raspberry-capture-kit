#!python3
try:
	import pyrealsense2.pyrealsense2 as rs
except ModuleNotFoundError:
	import pyrealsense2 as rs

import numpy as np
import cv2
import os
import json
import time
import sys
import platform
import asyncio
from timeit import default_timer as timer

import multiprocessing.queues as mpq
from multiprocessing import Process, Queue
import multiprocessing as mp

from flask import Flask, Response, render_template, send_from_directory
from flask_socketio import SocketIO, emit

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst
import traceback


#workaround for running this on macos
#https://stackoverflow.com/a/24941654
#https://stackoverflow.com/q/39496554
class XQueue(mpq.Queue):

    def __init__(self,*args,**kwargs):
        ctx = mp.get_context()
        super(XQueue, self).__init__(*args, **kwargs, ctx=ctx)

    def empty(self):
        try:
            return self.qsize() == 0
        except NotImplementedError:  # OS X -- see qsize() implementation
            return super(XQueue, self).empty()

class RealsenseCapture (mp.Process):

    def __init__(self, rtmp_uri, config_json, w, h, previewQueue, statusQueue, messageQueue):
        mp.Process.__init__(self)

        self.exit = mp.Event()
        self.rtmp_url = rtmp_uri
        self.json_file = config_json
        self.width = w
        self.height = h
        self.previewQueue = previewQueue
        self.statusQueue = statusQueue
        self.messageQueue = messageQueue
        self.rspipeline = None
        self.framecount = 0

        print ("Initialized Realsense Capture")

    def shutdown(self):
        print ("Shutdown Realsense Capture")
        self.exit.set()

    def loadConfiguration(self,profile, json_file):
        dev = profile.get_device()
        advnc_mode = rs.rs400_advanced_mode(dev)
        print("Advanced mode is", "enabled" if advnc_mode.is_enabled() else "disabled")
        json_obj = json.load(open(json_file))
        json_string = str(json_obj).replace("'", '\"')
        advnc_mode.load_json(json_string)

        while not advnc_mode.is_enabled():
            print("Trying to enable advanced mode...")
            advnc_mode.toggle_advanced_mode(True)

            # At this point the device will disconnect and re-connect.
            print("Sleeping for 5 seconds...")
            time.sleep(5)

            # The 'dev' object will become invalid and we need to initialize it again
            dev = profile.get_device()
            advnc_mode = rs.rs400_advanced_mode(dev)
            print("Advanced mode is", "enabled" if advnc_mode.is_enabled() else "disabled")
            advnc_mode.load_json(json_string)

    def spatial_filtering(self,depth_frame, magnitude=2, alpha=0.5, delta=20, holes_fill=0):
        spatial = rs.spatial_filter()
        spatial.set_option(rs.option.filter_magnitude, magnitude)
        spatial.set_option(rs.option.filter_smooth_alpha, alpha)
        spatial.set_option(rs.option.filter_smooth_delta, delta)
        spatial.set_option(rs.option.holes_fill, holes_fill)
        depth_frame = spatial.process(depth_frame)
        return depth_frame

    def hole_filling(self,depth_frame):
        hole_filling = rs.hole_filling_filter()
        depth_frame = hole_filling.process(depth_frame)
        return depth_frame

    def run(self):
        # ========================
        # 1. Configure all streams
        # ========================
        self.rspipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, 30)
        config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, 30)

        # ======================
        # 2. Start the streaming
        # ======================
        print("Starting up the Intel Realsense...")
        print("")
        profile = self.rspipeline.start(config)

        # Load the configuration here
        self.loadConfiguration(profile, self.json_file)

        # =================================
        # 3. The depth sensor's depth scale
        # =================================
        depth_sensor = profile.get_device().first_depth_sensor()
        depth_scale = depth_sensor.get_depth_scale()
        print("Depth Scale is: ", depth_scale)
        print("")

        # ==========================================
        # 4. Create an align object.
        #    Align the depth image to the rgb image.
        # ==========================================
        align_to = rs.stream.depth
        align = rs.align(align_to)

        try:
            # ===========================================
            # 5. Skip the first 30 frames.
            # This gives the Auto-Exposure time to adjust
            # ===========================================
            #for x in range(30):
            #    frames = self.rspipeline.wait_for_frames()
            #    # Align the depth frame to color frame
            #    aligned_frames = align.process(frames)

            print("Intel Realsense started successfully.")
            print("")

            #self.gstreamer = GStreamerSender(self.rtmp_url, self.width, self.height, self.statusQueue, self.messageQueue)
            #print("initialized")
            #self.gstreamer.start()

            intrinsics = True
            
            while not self.exit.is_set():
                # ======================================
                # 7. Wait for a coherent pair of frames:
                # ======================================
                start = timer()
                frames = self.rspipeline.wait_for_frames(1000)
                #waitFrameTime = timer()
                #print(str(waitFrameTime-start) + " Wait frame time")

                # =======================================
                # 8. Align the depth frame to color frame
                # =======================================
                aligned_frames = align.process(frames)

                # ================================================
                # 9. Fetch the depth and colour frames from stream
                # ================================================
                depth_frame = aligned_frames.get_depth_frame()
                color_frame = aligned_frames.get_color_frame()
                if not depth_frame or not color_frame:
                    pass

                # print the camera intrinsics just once. it is always the same
                if intrinsics:
                    print("Intel Realsense Camera Intrinsics: ")
                    print("========================================")
                    print(depth_frame.profile.as_video_stream_profile().intrinsics)
                    print(color_frame.profile.as_video_stream_profile().intrinsics)
                    print("")
                    intrinsics = False

                # =====================================
                # 10. Apply filtering to the depth image
                # =====================================
                # Apply a spatial filter without hole_filling (i.e. holes_fill=0)
                # depth_frame = self.spatial_filtering(depth_frame, magnitude=2, alpha=0.5, delta=10, holes_fill=1)
                # Apply hole filling filter
                # depth_frame = self.hole_filling(depth_frame)

                # ==================================
                # 11. Convert images to numpy arrays
                # ==================================
                depth_image = np.asanyarray(depth_frame.get_data())
                color_image = np.asanyarray(color_frame.get_data())

                # ======================================================================
                # 12. Conver depth to hsv
                # ==================================
                # We need to encode/pack the 16bit depth value to RGB
                # we do this by treating it as the Hue in HSV. 
                # we then encode HSV to RGB and stream that
                # on the other end we reverse RGB to HSV, H will give us the depth value back.
                # HSV elements are in the 0-1 range so we need to normalize the depth array to 0-1
                # First set a far plane and set everything beyond that to 0

                clipped = depth_image > 4000
                depth_image[clipped] = 0

                # Now normalize using that far plane
                # cv expects the H in degrees, not 0-1 :(
                depth_image_norm = (depth_image * (360/4000)).astype( np.float32)

                # Create 3 dimensional HSV array where H=depth, S=1, V=1
                depth_hsv = np.concatenate([depth_image_norm[..., np.newaxis]]*3, axis=2)
                #depth_hsv[:,:,0] = 1
                depth_hsv[:,:,1] = 1
                depth_hsv[:,:,2] = 1

                discard = depth_image_norm == 0
                s = depth_hsv[:,:,1]
                v = depth_hsv[:,:,2] 
                s[ discard] = 0
                v[ discard] = 0

                # cv2.cvtColor to convert HSV to RGB
                # problem is that cv2 expects hsv to 8bit (0-255)
                hsv = cv2.cvtColor(depth_hsv, cv2.COLOR_HSV2BGR)
                hsv8 = (hsv*255).astype( np.uint8)

                # Stack rgb and depth map images horizontally for visualisation only
                #images = np.vstack((color_image, hsv8))

                # push to gstreamer
                #frame = images.tostring()
                #start = timer()
                #buf = Gst.Buffer.new_allocate(None, len(frame), None)
                #buffAllocationTime = timer()
                #print(str(buffAllocationTime-start) + " buffer allocation time")
                #buf.fill(0,frame)
                #start = timer()
                #appsrc.emit("push-buffer", buf)
                self.messageQueue.put_nowait((color_image,hsv8))
                #emitTime = timer()
                #print(str(emitTime-start) + " push stream")


                #preview side by side because of landscape orientation of the pi 

                #if we don't check for exit here the shutdown process hangs here
                #start = timer()
                if(not self.exit.is_set()):
                    try:
                        if(not self.previewQueue.full()):
                            self.previewQueue.put_nowait((color_image, hsv8))
                    except:
                        pass
                opencvWindowTimer = timer()
                print(str(opencvWindowTimer - start) + " opencv window time")

        except:        
            e = sys.exc_info()[0]
            print( "Unexpected Error: %s" % e )
            self.statusQueue.put_nowait("ERROR: Unexpected Error: %s" % e)

        finally:
            # Stop streaming
            print( "Stop realsense pipeline" )
            self.rspipeline.stop()
            print( "Pause gstreamer pipe" )
    
        
        self.statusQueue.put_nowait("INFO: Exiting Realsense Capture process")
        print ("Exiting capture loop")

