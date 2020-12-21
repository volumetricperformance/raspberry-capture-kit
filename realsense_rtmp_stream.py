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

class GStreamerSender(mp.Process):
    def __init__(self, rtmp_url, width, height, statusQueue, messageQueue):
        mp.Process.__init__(self)

        self.rtmp_url = rtmp_url
        self.width = width
        self.height = height
        self.messageQueue = messageQueue
        self.statusQueue = statusQueue
        self.exit = mp.Event()
        print("initialized")

    def run(self):
        # ===========================================
        # 6. Setup gstreamer
        # Usefull gst resources / cheatsheets
        # https://github.com/matthew1000/gstreamer-cheat-sheet/blob/master/rtmp.md
        # http://wiki.oz9aec.net/index.php/Gstreamer_cheat_sheet
        # https://github.com/matthew1000/gstreamer-cheat-sheet/blob/master/mixing.md
        # ===========================================     
        CLI = ''
        caps =  'caps="video/x-raw,format=BGR,width='+str(self.width)+',height='+ str(self.height*2) + ',framerate=(fraction)30/1,pixel-aspect-ratio=(fraction)1/1"'
        
        if platform.system() == "Linux":
            #assuming Linux means RPI
            
            CLI='flvmux name=mux streamable=true latency=3000000000 ! rtmpsink location="'+  self.rtmp_url +' live=1 flashver=FME/3.0%20(compatible;%20FMSc%201.0)" \
                appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE '+ str(caps) +' ! \
                videoconvert !  omxh264enc ! h264parse ! video/x-h264 ! \
                queue max-size-buffers=0 max-size-bytes=0 max-size-time=180000000 min-threshold-buffers=1 leaky=upstream ! mux. \
                alsasrc ! audio/x-raw, format=S16LE, rate=44100, channels=1 ! voaacenc bitrate=44100 ! aacparse ! audio/mpeg, mpegversion=4 ! \
                queue max-size-buffers=0 max-size-bytes=0 max-size-time=4000000000 min-threshold-buffers=1 ! mux.'

        elif platform.system() == "Darwin":
            #macos
            #CLI='flvmux name=mux streamable=true ! rtmpsink location="'+  self.rtmp_url +' live=1 flashver=FME/3.0%20(compatible;%20FMSc%201.0)" \
            #    appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE '+ str(caps) +' ! \
            #    videoconvert ! vtenc_h264 ! video/x-h264 ! h264parse ! video/x-h264 ! \
            #    queue max-size-buffers=4 ! flvmux name=mux. \
            #    osxaudiosrc do-timestamp=true ! audioconvert ! audioresample ! audio/x-raw,rate=48000 ! faac bitrate=48000 ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! \
            #    queue max-size-buffers=4 ! mux.'

            CLI='appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE caps="video/x-raw,format=BGR,width='+str(self.width)+',height='+ str(self.height*2) + ',framerate=(fraction)30/1,pixel-aspect-ratio=(fraction)1/1" ! videoconvert ! vtenc_h264 ! video/x-h264 ! h264parse ! video/x-h264 ! queue max-size-buffers=4 ! flvmux name=mux ! rtmpsink location="'+ self.rtmp_url +'" sync=true   osxaudiosrc do-timestamp=true ! audioconvert ! audioresample ! audio/x-raw,rate=48000 ! faac bitrate=48000 ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! queue max-size-buffers=4 ! mux.' 


        #TODO: windows

        print( CLI )
        self.gstpipe=Gst.parse_launch(CLI)
        #Set up a pipeline bus watch to catch errors.
        self.bus = self.gstpipe.get_bus()
        self.bus.connect("message", self.on_bus_message)
        self.appsrc=self.gstpipe.get_by_name("mysource")
        self.appsrc.set_property('emit-signals',True) #tell sink to emit signals 
        self.gstpipe.set_state(Gst.State.PLAYING)

        print("Starting message loop")
        buff = None
        while not self.exit.is_set():
            try:
                while(not self.messageQueue.empty()):
                    frame = self.messageQueue.get()
                    if buff is None:
                        buff = Gst.Buffer.new_allocate(None, len(frame), None)
                    buff.fill(0,frame)
                    self.appsrc.emit("push-buffer", buff)
                    #process any messages from gstreamer
                    #start = timer()
                    msg = self.bus.pop_filtered(
                        Gst.MessageType.ERROR | Gst.MessageType.WARNING | Gst.MessageType.EOS | Gst.MessageType.INFO | Gst.MessageType.STATE_CHANGED
                    )
                    #msgprocesstime = timer()
                    #print(str(msgprocesstime-start) + " gstreamer process time")
                    #empty the message queue if there is one
                    #start = timer()
                    while( msg ): 
                        self.on_bus_message(msg)
                        msg = self.bus.pop_filtered(
                            Gst.MessageType.ERROR | Gst.MessageType.WARNING | Gst.MessageType.EOS | Gst.MessageType.INFO | Gst.MessageType.STATE_CHANGED
                        )

                    #msgprocesstime = timer()
                    #print(str(msgprocesstime-start) + " gstreamer message queue time")
            except queue.Empty:
                time.sleep(0.02)
        try:
            if( self.gstpipe.get_state()[1] is not Gst.State.PAUSED ):
                self.gstpipe.set_state(Gst.State.PAUSED)
        except:
            self.statusQueue.put_nowait("ERROR: Error pausing gstreamer")
            print ("Error pausing gstreamer")    


    def shutdown(self):
        self.exit.set()

    def on_bus_message(self, message):
        t = message.type
        
        print('{} {}: {}'.format(
                Gst.MessageType.get_name(message.type), message.src.name,
                message.get_structure().to_string()))

        if t == Gst.MessageType.EOS:
            print("Eos")
            self.statusQueue.put_nowait('WARNING: End of Stream')

        elif t == Gst.MessageType.INFO:
            self.statusQueue.put_nowait('INFO: %s, %s' % (msg.src.name, msg.get_structure().to_string()))

        elif t == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            #print("Pipeline state changed from %s to %s." %  (old_state.value_nick, new_state.value_nick))
            self.statusQueue.put_nowait("STREAM_STATE_CHANGED: %s, %s, %s" % (message.src.name, old_state.value_nick, new_state.value_nick))

        elif t == Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            print('Warning: %s: %s\n' % (err, debug))
            self.statusQueue.put_nowait('WARNING: %s, %s' % (err, debug) )
            #sys.stderr.write('Warning: %s: %s\n' % (err, debug))
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print('Error: %s: %s\n' % (err, debug))
            self.statusQueue.put_nowait('ERROR: %s, %s' % (err, debug) )
            self.shutdown()
            #sys.stderr.write('Error: %s: %s\n' % (err, debug))       
        return True


class RealsenseCapture (mp.Process):

    def __init__(self, rtmp_uri, config_json, w, h, previewQueue, statusQueue):
        mp.Process.__init__(self)

        self.exit = mp.Event()
        self.rtmp_url = rtmp_uri
        self.json_file = config_json
        self.width = w
        self.height = h
        self.previewQueue = previewQueue
        self.statusQueue = statusQueue
        self.gstpipe = None
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

            messageQueue = Queue()
            self.gstreamer = GStreamerSender(self.rtmp_url, self.width, self.height, self.statusQueue, messageQueue)
            print("initialized")
            self.gstreamer.start()
            time.sleep(0.5)

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
                images = np.vstack((color_image, hsv8))

                # push to gstreamer
                #frame = images.tostring()
                #start = timer()
                #buf = Gst.Buffer.new_allocate(None, len(frame), None)
                #buffAllocationTime = timer()
                #print(str(buffAllocationTime-start) + " buffer allocation time")
                #buf.fill(0,frame)
                #start = timer()
                #appsrc.emit("push-buffer", buf)
                messageQueue.put_nowait(images.tostring())
                #emitTime = timer()
                #print(str(emitTime-start) + " push stream")


                #preview side by side because of landscape orientation of the pi 

                #if we don't check for exit here the shutdown process hangs here
                #start = timer()
                if(not self.exit.is_set()):
                    self.previewQueue.put_nowait(np.hstack((color_image, hsv8)))
                opencvWindowTimer = timer()
                print(str(opencvWindowTimer - start) + " opencv window time")

        except:        
            e = sys.exc_info()[0]
            print( "Unexpected Error: %s" % e )
            self.statusQueue.put_nowait("ERROR: Unexpected Error: %s" % e)

        finally:
            # Stop streaming
            self.gstreamer.shutdown()
            print( "Stop realsense pipeline" )
            self.rspipeline.stop()
            print( "Pause gstreamer pipe" )
    
        
        self.statusQueue.put_nowait("INFO: Exiting Realsense Capture process")
        print ("Exiting capture loop")

