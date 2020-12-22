#!python3
import numpy as np
import cv2
import os
import json
import time
import sys
import platform
import asyncio

import multiprocessing.queues as mpq
from multiprocessing import Process, Queue
import multiprocessing as mp

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

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
                    (color,depth) = self.messageQueue.get_nowait()
                    image = np.vstack((color, depth))
                    frame = image.tostring()
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
                pass
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
