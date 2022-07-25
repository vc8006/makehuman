#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Modifier taskview

**Project Name:**      MakeHuman

**Product Home Page:** http://www.makehumancommunity.org/

**Github Code Home Page:**    https://github.com/makehumancommunity/

**Authors:**           Glynn Clements, Jonas Hauquier

**Copyright(c):**      MakeHuman Team 2001-2020

**Licensing:**         AGPL3

    This file is part of MakeHuman Community (www.makehumancommunity.org).

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as
    published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.


Abstract
--------

Common taskview for managing modifier sliders
"""

import gui
import gui3d
import humanmodifier
import modifierslider
import getpath
from core import G
import log
from collections import OrderedDict
import language
import collections
from mesh_operations import calculateSurface

from logging import *
LOG_FORMAT = "[%(asctime)s] [%(filename)s:%(lineno)s - %(funcName)s() ] %(message)s"
# LOG_FORMAT = '%m-%d %H:%M:%S','[%(asctime)s] {%(pathname)s:%(lineno)d} %(funcName)s - %(message)s'
basicConfig(filename="allLogs.log",level = DEBUG,format=LOG_FORMAT)

import log
class ModifierTaskView(gui3d.TaskView):
    def __init__(self, category, name, label=None, saveName=None, cameraView=None):
        debug("log")
        if label is None:
            label = name.capitalize()
        if saveName is None:
            saveName = name

        super(ModifierTaskView, self).__init__(category, name, label=label)

        self.saveName = saveName
        self.cameraFunc = _getCamFunc(cameraView)

        self.groupBoxes = OrderedDict()
        self.radioButtons = []
        self.sliders = []
        self.modifiers = {}

        self.categoryBox = self.addRightWidget(gui.GroupBox('Category'))
        self.groupBox = self.addLeftWidget(gui.StackedBox())

        self.showMacroStats = False
        self.human = gui3d.app.selectedHuman

    def addSlider(self, sliderCategory, slider, enabledCondition=None):
        debug("log")
        # Get category groupbox
        categoryName = sliderCategory.capitalize()
        if categoryName not in self.groupBoxes:
            # Create box
            box = self.groupBox.addWidget(gui.GroupBox(categoryName))
            self.groupBoxes[categoryName] = box

            # Create radiobutton
            isFirstBox = len(self.radioButtons) == 0
            self.categoryBox.addWidget(GroupBoxRadioButton(self, self.radioButtons, categoryName, box, selected=isFirstBox))
            if isFirstBox:
                self.groupBox.showWidget(list(self.groupBoxes.values())[0])
        else:
            box = self.groupBoxes[categoryName]

        # Add slider to groupbox
        self.modifiers[slider.modifier.fullName] = slider.modifier
        if slider.modifier.description is not None and slider.modifier.description != "":
            slider.setToolTip(slider.modifier.description)
        box.addWidget(slider)
        slider.enabledCondition = enabledCondition
        self.sliders.append(slider)

    def updateMacro(self):
        debug("log")
        self.human.updateMacroModifiers()

    def getModifiers(self):
        debug("log")
        return self.modifiers

    def onShow(self, event):
        debug("log")
        gui3d.TaskView.onShow(self, event)

        # Only show macro statistics in status bar for Macro modeling task
        # (depends on the correct task name being defined)
        if self.showMacroStats:
            self.showMacroStatus()

        if G.app.getSetting('cameraAutoZoom'):
            self.setCamera()

        self.syncSliders()

    def syncSliders(self):
        debug("log")
        for slider in self.sliders:
            slider.update()
            if slider.enabledCondition:
                enabled = getattr(slider.modifier.human, slider.enabledCondition)()
                slider.setEnabled(enabled)

    def onHide(self, event):
        debug("log")
        super(ModifierTaskView, self).onHide(event)

        if self.name == "Macro modelling":
            self.setStatus('')

    def onHumanChanged(self, event):
        debug("log")
        # Update sliders to modifier values
        self.syncSliders()

        if event.change in ('reset', 'load', 'random'):
            self.updateMacro()

        if self.showMacroStats and self.isVisible():
            self.showMacroStatus()

    def loadHandler(self, human, values, strict):
        debug("log")
        pass

    def saveHandler(self, human, file):
        debug("log")
        pass

    def setCamera(self):
        debug("log")
        if self.cameraFunc:
            f = getattr(G.app, self.cameraFunc)
            f()

    def showMacroStatus(self):
        debug("log")
        human = G.app.selectedHuman

        if human.getGender() == 0.0:
            gender = G.app.getLanguageString('female')
        elif human.getGender() == 1.0:
            gender = G.app.getLanguageString('male')
        elif abs(human.getGender() - 0.5) < 0.01:
            gender = G.app.getLanguageString('neutral')
        else:
            gender = G.app.getLanguageString('%.2f%% female, %.2f%% male') % ((1.0 - human.getGender()) * 100, human.getGender() * 100)

        age = human.getAgeYears()
        muscle = (human.getMuscle() * 100.0)
        height = human.getHeightCm()
        if not G.app.getSetting('real_weight'):
            weight = (50 + (150 - 50) * human.getWeight())
            w_units = '%'
        else:
            weight = human.getWeightKg()

        if G.app.getSetting('units') == 'metric':
            l_units = 'cm'
            if G.app.getSetting('real_weight'):
                w_units = 'kg'
        else:
            l_units = 'in.'
            height *= 0.393700787
            if G.app.getSetting('real_weight'):
                w_units = 'lb.'
                weight *= 2.20462

        self.setStatus([ ['Gender',': %s  '], ['Age',': %d  '], ['Muscle',': %.2f %%  '], ['Weight',': %.2f %s  '], ['Height',': %.2f %s'] ], gender, age, muscle, weight, w_units, height, l_units)

    def setStatus(self, format, *args):
        debug("log")
        G.app.statusPersist(format, *args)


class GroupBoxRadioButton(gui.RadioButton):
    def __init__(self, task, group, label, groupBox, selected=False):
        debug("log")
        super(GroupBoxRadioButton, self).__init__(group, label, selected)
        self.groupBox = groupBox
        self.task = task

    def onClicked(self, event):
        debug("log")
        self.task.groupBox.showWidget(self.groupBox)
        #self.task.onSliderFocus(self.groupBox.children[0]) # TODO needed for measurement


def _getCamFunc(cameraName):
    if cameraName:
        if hasattr(gui3d.app, cameraName) and isinstance(getattr(gui3d.app, cameraName), collections.abc.Callable):
            return cameraName

        return "set" + cameraName.upper()[0] + cameraName[1:]
    else:
        return None

 

def loadModifierTaskViews(filename, human, category, taskviewClass=None):
    debug("log")
    """
    Create modifier task views from modifiersliders defined in slider definition
    file.
    """
    import json

    if not taskviewClass:
        taskviewClass = ModifierTaskView

    data = json.load(open(filename, 'r', encoding='utf-8'), object_pairs_hook=OrderedDict)
    taskViews = []
    # Create task views
    print("from data/modifiers/modeling_sliders.json file we are getting values at guimodiifier.py")
    for taskName, taskViewProps in data.items():

        # print('printing tasksName from guimodifier.py /////////////\\\\\\\\\ ',taskName)

        sName = taskViewProps.get('saveName', None)
        label = taskViewProps.get('label', None)
        taskView = taskviewClass(category, taskName, label, sName)
        taskView.sortOrder = taskViewProps.get('sortOrder', None)
        taskView.showMacroStats = taskViewProps.get('showMacroStats', None)
        category.addTask(taskView)

        # Create sliders
        for sliderCategory, sliderDefs in taskViewProps['modifiers'].items():
            # print("printing sliderCatory --------> ",sliderCategory)
            for sDef in sliderDefs:
                modifierName = sDef['mod']
                modifier = human.getModifier(modifierName)
                label = sDef.get('label', None)
                camFunc = _getCamFunc( sDef.get('cam', None))
                tooltip = None
                if len(modifier.description) > 0:
                    tooltip=modifier.description
                slider = modifierslider.ModifierSlider(modifier, label=label, cameraView=camFunc, tooltip=tooltip)
                enabledCondition = sDef.get("enabledCondition", None)
                taskView.addSlider(sliderCategory, slider, enabledCondition)

        if taskView.saveName is not None:
            gui3d.app.addLoadHandler(taskView.saveName, taskView.loadHandler)
            gui3d.app.addSaveHandler(taskView.saveHandler)

        taskViews.append(taskView)

    return taskViews
