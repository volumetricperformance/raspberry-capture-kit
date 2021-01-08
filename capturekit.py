#!python3
try:
	import pyrealsense2.pyrealsense2 as rs
except ModuleNotFoundError:
	print('Use local realsense lib')
	import pyrealsense2 as rs

import numpy as np
import cv2
import os
import json
import time
import platform
import atexit
import asyncio
import netifaces
import requests
from timeit import default_timer as timer

from threading import Thread

import multiprocessing
from multiprocessing import Process, Queue
import multiprocessing.queues as mpq
from multiprocessing import Process, SimpleQueue

import flask
from flask import Flask, Response, render_template, send_from_directory
from flask_socketio import SocketIO, emit
from realsense_rtmp_stream import RealsenseCapture
from gstreamer_sender import GStreamerSender

from colorama import Fore, Back, Style
from colorama import init
init()

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

streams = []
running = False
streaming = False

hostip = ""

#queue of images
previewQueue = None
#queue of status messages
statusQueue = None
#queue of messages
messageQueue = None


app = Flask(__name__, 
    static_folder='web', 
    static_url_path='')

#TODO: threading is not ideas but it's the only one we can get to work with multiprocessing without reverting to needing proper message queue like rabbitmq    
socketio = SocketIO(app, async_mode="threading")

current_dir = os.path.dirname(os.path.realpath(__file__))
os.environ["GST_DEBUG_DUMP_DOT_DIR"] = current_dir
os.putenv('GST_DEBUG_DUMP_DIR_DIR', current_dir)
os.putenv('GST_DEBUG_NO_COLOR', "1")
os.putenv('GST_DEBUG_FILE', current_dir + '/debug.log')
os.putenv('GST_DEBUG', '2,*error*:4')

Gst.init(None)
#Gst.debug_set_active(True)
#Gst.debug_set_default_threshold(4)

@socketio.on('message')
def handle_message(message):
    print('received message: ' + message)

@socketio.on('connect')
def test_connect():
    emit('my response', {'data': 'Connected'})

@socketio.on('disconnect')
def test_disconnect():
    print('Client disconnected')    

@socketio.on('start')
def handle_start(url):

    global streams
    global streaming

    print('start ', url, len(streams))

    if len(streams) == 0 and streaming == False:
        # Control parameters
        # =======================
        dir_path = os.path.dirname(os.path.realpath(__file__))
        json_file = dir_path + "/" + "MidResHighDensityPreset.json" # MidResHighDensityPreset.json / custom / MidResHighAccuracyPreset

        gstMessager = GStreamerSender( url, 640, 480, statusQueue, previewQueue)
        stream = RealsenseCapture( url, json_file, 640, 480, statusQueue, gstMessager.messageQueue )
        streaming = True        
        stream.start()
        streams.append(stream)
        gstMessager.start()
        streams.append(gstMessager)


@socketio.on('stop')
def handle_stop():
    global streams
    global streaming
    
    print('Stop')
    
    if len(streams) > 0:
        for p in streams:
            p.shutdown()

        #because we have forked processes we need terminate them, they don't terminate of their own accord
        #it takes a while for gstreamer to exit, so we have a timer here

        #you can't start a stream while this is in process
        TIMEOUT = 4
        start = time.time()
        while time.time() - start <= TIMEOUT:
            if not any(p.is_alive() for p in streams):
                # All the processes are done, break now.
                break

            time.sleep(.1)  # Just to avoid hogging the CPU
        else:
            # We only enter this if we didn't 'break' above.
            print("timed out, killing all processes")
            for p in streams:
                p.terminate()
                p.join()
                
        streams.clear()
        streaming = False

@app.route('/')
def root():
    print('route')  
    return app.send_static_file('index.html')

#TODO: Add some kind of security step here? Anybody on the local network can shut down hardware
@app.route('/shutdown')
def quit():
    global running
    print('/shutdown %s' % (running))

    running = False

    try:
        socketio.stop()
    except:
        pass

    return (' ', 200) 

#TODO: Add some kind of security step here? Anybody on the local network can shut down hardware
@socketio.on('reboot')
def handle_reboot():
    global running
    
    print('Reboot %s' % (running))
    running = False
    try:
        socketio.stop()
    except:
        pass

    if platform.system() == "Linux":
        os.system('systemctl reboot -i')


@socketio.on('shutdown')
def handle_shutdown():
    global running
    
    print('Shutdown %s' % (running))
    running = False
    try:
        socketio.stop()
    except:
        pass

    if platform.system() == "Linux":
        os.system('systemctl poweroff -i')        
  
class WebSocketServer(object):
    def __init__(self):
        self.thread = None

    def start_server(self):
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)

    def start(self):
        self.thread = socketio.start_background_task(self.start_server)
       	socketio.start_background_task(self.send_status)

    def send_status(self):
        
        global streams
        global running        
        
        while (running==True):
            if( len(streams)>0):
                try:
                    status = Status()
                    if( status is not None ):
                        #print('status: %s' % (status) )
                        status = Status()
                        socketio.emit("status", status)
                except:
                    print('WebSocketServer send_status status exception')
                    pass   
            try:
                socketio.sleep(0.01)
            except:
                print('WebSocketServer send_status sleep exception')
                pass    

        print('Exit WebSocketServer')

def Status():
    result = None
    try:
        if( not statusQueue.empty() ):
            result = statusQueue.get_nowait()
    except queue.Empty:
        pass

    return result

def LastPreview():
    result = None

    try:
        while( not previewQueue.empty() ):
            (color,depth) = previewQueue.get_nowait()
    except queue.Empty:
        pass

    #result = np.hstack((color,depth))
    result = depth
    return result


def main():
    GObject.threads_init()

    global streams
    global streaming
    global running
    
    global previewQueue
    global statusQueue
    global messageQueue

    atexit.register(term_stream, streams)

    #queue of images
    previewQueue = Queue(maxsize=3)
    #queue of status messages
    statusQueue = Queue(maxsize=1000)

    try:
        log = ''
        print( "Default gateway: ", netifaces.gateways()['default'])
        print( "Internet interface", netifaces.gateways()['default'][netifaces.AF_INET])

        if( len(netifaces.gateways()['default'])):
            if( len( netifaces.gateways()['default'][netifaces.AF_INET])):
                iface = netifaces.gateways()['default'][netifaces.AF_INET][1]
                if( len(netifaces.ifaddresses(iface)[netifaces.AF_INET] )):
                    hostip = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]['addr']
                    print(Fore.YELLOW + "Found Host IP" , hostip , Fore.RESET)
                    running = True
                else:
                    log += "No internet connected address \r\n"            
                    print(Fore.RED + "No internet connected address [AF_INET]"+ Fore.RESET)
            else:
                log += "No internet connected gateway \r\n"            
                print(Fore.RED + "No internet connected gateway"+ Fore.RESET)
        else:
            log += "No default gateway \r\n"            
            print(Fore.RED + "No default gateway"+ Fore.RESET)


        ctx = rs.context()
        if len(ctx.devices) > 0:
            for d in ctx.devices:
                print ('Found device: ',
                    d.get_info(rs.camera_info.name), ' ',
                    d.get_info(rs.camera_info.serial_number))
        else:
            log = "No Realsense devices detected"            
            print(Fore.RED + log  + Fore.RESET)
            running = False

        WINDOW_NAME	= 'VPT Kit'

        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_GUI_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, 1280, 720)
        cv2.moveWindow(WINDOW_NAME, 0, 0)

        uiframe = np.zeros((720, 1280, 3), np.uint8)      
        uiframe[:] = (50, 50, 50)  

        preview = np.zeros((480, 640, 3), np.uint8)
        color = np.zeros((480, 640, 3), np.uint8)
        depth = np.zeros((480, 640, 3), np.uint8)
        server = WebSocketServer()
        server.start()
        
        if( running ):

            while(running == True):
            
                try:
                    #TODO: need better way to keep streams updated / monitor when the process crashes/exits
                    #TODO: need thread locking around streams because another thread migh have broken it

                    if len(streams) > 0:                                            
                        #recording / red
                        uiframe[:] = (50, 50, 175) 
                        depth[:] = (0,0,0)
                        try:
                            if not previewQueue.empty():
                                (color,depth) = previewQueue.get(block=False)
                        except queue.Empty:
                            pass
                    else:
                        depth[:] = (0,0,0)
                        uiframe[:] = (50, 50, 50)  
                except:
                    pass
    
                y = 120
                uiframe[y:y+480, 320:640+320] = depth
                #uiframe[y:y+480, 640:1280] = color

                # Using cv2.putText() method 
                uiframe = cv2.putText(uiframe, 'http://{0}:5000/'.format( hostip), (50,100), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (255, 255, 255) , 4, cv2.LINE_AA)

                cv2.imshow(WINDOW_NAME, uiframe) 
                
                # Check if ESC key was pressed
                if cv2.waitKey(1) == 27:
                    running = False
                    break

                socketio.sleep(0.2)

        else:
                uiframe[:] = (0, 165, 255)  
                uiframe = cv2.putText(uiframe, log, (50,100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0) , 4, cv2.LINE_AA)
                running = True
                while(running == True):
                    cv2.imshow(WINDOW_NAME, uiframe) 
                    # Check if ESC key was pressed
                    if cv2.waitKey(1) == 27:
                        running = False

    finally:
        print('shutting down')  

        if len(streams) > 0:
            streaming = False
            print('shutdown stream')  
            streams[0].shutdown()
            streams[1].shutdown()
            
        try:
            shutdown_server = requests.get("http://localhost:5000/shutdown", data=None)
        except:
            print('exception shutting down')  
            pass
    
    print('Done?')

def term_stream(streams):
    if len(streams) > 0:
        streams[0].terminate()
        streams[1].terminate()

if __name__ == '__main__':
    multiprocessing.set_start_method('spawn')    
    main()
    print('Done!')
