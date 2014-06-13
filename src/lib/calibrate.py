#!/usr/bin/env python
# -*- coding: us-ascii -*-
# generated by wxGlade 0.6.3 on Sat Feb  6 08:25:38 2010

""" =====================================================================================
    calibrate.py - A tool for finding the transformation between map and real coordinates
    =====================================================================================

    This script helps you experimentally determine the coordinate transformation
    between points on your region map and points in your localization system.

    The specific points used for calibration are chosen in the Region Editor.

    :Usage: ``calibrate.py [spec_file]``
"""

import wx, sys, os, socket
import fileMethods, regions, project, execute, handlerSubsystem
import logging
import globalConfig
from numpy import *
import mapRenderer
from _transformations import affine_matrix_from_points

# begin wxGlade: extracode
# end wxGlade

class CalibrateFrame(wx.Frame):
    def __init__(self, *args, **kwds):
        # begin wxGlade: CalibrateFrame.__init__
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        wx.Frame.__init__(self, *args, **kwds)
        self.panel_map = wx.Panel(self, -1, style=wx.SUNKEN_BORDER)
        self.label_instructions = wx.StaticText(self, -1, "Welcome to the LTLMoP Calibration Tool")
        self.button_go = wx.Button(self, -1, "Begin")

        self.__set_properties()
        self.__do_layout()

        self.Bind(wx.EVT_BUTTON, self.onButtonGo, self.button_go)
        # end wxGlade

        self.mapBitmap = None
        self.robotPos = None

        if len(sys.argv) < 2:
            print "You must specify a specification file."
            print "Usage: %s [spec_file]" % sys.argv[0]
            sys.exit(2)

        if len(sys.argv) == 3:
            self.configEditorPort = ('localhost', int(sys.argv[2]))
        else:
            self.configEditorPort = None

        # Update with this new project
        self.executor = execute.LTLMoPExecutor()
        self.proj = project.Project()
        self.proj.loadProject(sys.argv[1])
        self.executor.proj = self.proj
        self.hsub = handlerSubsystem.HandlerSubsystem(self.executor, self.proj.project_root)
        self.executor.hsub = self.hsub

        logging.info("Setting current executing config...")
        config, success = self.executor.hsub.loadConfigFile(self.proj.current_config)
        if success: self.executor.hsub.configs.append(config)
        self.executor.hsub.setExecutingConfig(self.proj.current_config)


        if self.proj.current_config != "calibrate":
            print "(ERROR) Calibration can only be run on a specification file with a calibration configuration.\nPlease use ConfigEditor to calibrate a configuration."
            sys.exit(3)

        # Initialize the init and pose handlers

        print "Importing handler functions..."
        logging.info("Instantiate all handlers...")
        self.hsub.instantiateAllHandlers()

        self.panel_map.SetBackgroundColour(wx.WHITE)
        self.panel_map.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)
        self.panel_map.Bind(wx.EVT_PAINT, self.onPaint)
        self.Bind(wx.EVT_SIZE, self.onResize, self)

        self.onResize(None)

        # Start timer for blinking
        self.robotPos = None
        self.markerPos = None
        self.timer = wx.Timer(self)
        self.timer.Start(500)
        self.Bind(wx.EVT_TIMER, self.moveRobot)

        self.calibrationWizard = self.doCalibration()

    def onResize(self, event):
        size = self.panel_map.GetSize()
        self.mapBitmap = wx.EmptyBitmap(size.x, size.y)
        self.mapScale = mapRenderer.drawMap(self.mapBitmap, self.proj.rfi, scaleToFit=True, drawLabels=True, memory=True)

        self.Refresh()
        self.Update()

        if event is not None:
            event.Skip()

    def onPaint(self, event=None):
        if self.mapBitmap is None:
            return

        if event is None:
            dc = wx.ClientDC(self.panel_map)
        else:
            pdc = wx.AutoBufferedPaintDC(self.panel_map)
            try:
                dc = wx.GCDC(pdc)
            except:
                dc = pdc

        dc.BeginDrawing()

        # Draw background
        dc.DrawBitmap(self.mapBitmap, 0, 0)

        # Draw robot
        if self.robotPos is not None:
            [x,y] = map(lambda x: int(self.mapScale*x), self.robotPos)
            dc.DrawCircle(x, y, 15)

        dc.EndDrawing()

        if event is not None:
            event.Skip()

    def setStepInfo(self, label, button):
        self.label_instructions.SetLabel(label)
        self.button_go.SetLabel(button)
        self.Layout()
        self.Refresh()

    def doCalibration(self):
        # Load the calibration points from region file

        pt_names = []
        file_pts = None
        for [name, index, x, y] in self.proj.rfi.getCalibrationPoints():
            pt_names.append(name + "_P" + str(index))
            new_pt = mat([float(x), float(y)]).T
            if file_pts is None:
                file_pts = new_pt
            else:
                file_pts = hstack([file_pts, new_pt])

        if file_pts is None or file_pts.shape[1] < 3:
            wx.MessageBox("Please choose at least three points in Region Editor for calibration.  Quitting.", "Error", wx.OK)
            self.Close()

        # Get real coordinates for calibration points
        real_pts = None
        for i, point in enumerate(file_pts.T):
            # Show blinking circle on map
            self.markerPos = point.tolist()[0]

            self.setStepInfo('Please place robot at Point %s shown on the map and press [Capture].' % pt_names[i], "Capture")
            yield

            self.markerPos = None # Disable blinking circle

            pose = self.hsub.getPose()

            new_pt = mat(pose[0:2]).T
            if real_pts is None:
                real_pts = new_pt
            else:
                real_pts = hstack([real_pts, new_pt])

            self.setStepInfo('Read real point %s coordinate of [%f, %f].' % (pt_names[i], pose[0], pose[1]), "Continue")
            yield

        # Calculate transformation:
        T = affine_matrix_from_points(real_pts, file_pts)

        self.setStepInfo("Calibration complete!", "Quit")

        # Sends the data back to Config Editor via UDP, or just print
        output = repr(T)

        if self.configEditorPort is None:
            print output
        else:
            UDPSock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            UDPSock.sendto(output, self.configEditorPort)
            UDPSock.close()

        yield

    def moveRobot(self, event, state=[False]):
        if self.markerPos is not None:
            if not state[0]:
                self.robotPos = None
            else:
                self.robotPos = self.markerPos

            self.onPaint()
            state[0] = not state[0]

    def __set_properties(self):
        # begin wxGlade: CalibrateFrame.__set_properties
        self.SetTitle("Calibration Tool")
        self.SetSize((898, 632))
        self.label_instructions.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.NORMAL, 0, "Lucida Grande"))
        self.button_go.SetDefault()
        # end wxGlade

    def __do_layout(self):
        # begin wxGlade: CalibrateFrame.__do_layout
        sizer_1 = wx.BoxSizer(wx.VERTICAL)
        sizer_2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_1.Add(self.panel_map, 1, wx.EXPAND, 0)
        sizer_1.Add((20, 15), 0, 0, 0)
        sizer_2.Add((15, 20), 0, 0, 0)
        sizer_2.Add(self.label_instructions, 1, 0, 0)
        sizer_2.Add(self.button_go, 0, 0, 0)
        sizer_2.Add((15, 20), 0, 0, 0)
        sizer_1.Add(sizer_2, 0, wx.EXPAND, 0)
        sizer_1.Add((20, 15), 0, 0, 0)
        self.SetSizer(sizer_1)
        self.Layout()
        # end wxGlade

    def onButtonGo(self, event): # wxGlade: CalibrateFrame.<event_handler>
        try:
            self.calibrationWizard.next()
        except StopIteration:
            wx.CallAfter(self.Close)

# end of class CalibrateFrame


class CalibrateApp(wx.App):
    def OnInit(self):
        wx.InitAllImageHandlers()
        frame_1 = CalibrateFrame(None, -1, "")
        self.SetTopWindow(frame_1)
        frame_1.Show()
        return 1

# end of class CalibrateApp

if __name__ == "__main__":
    calibrate = CalibrateApp(0)
    calibrate.MainLoop()
