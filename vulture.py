from svgpathtools import Line, QuadraticBezier, CubicBezier, Path, Arc, svg2paths2
from svgelements import Path as elPath, Matrix
import numpy as np
import argparse
import svgwrite
import bezier #pip install bezier
import math
import subprocess
import os
import sys
import re
import xml.etree.ElementTree as XMLET
import shlex
import time

# Takes an x/y tuple and returns a complex number
def tuple_to_imag(t):
    return t[0] + t[1] * 1j

# Global variables (most of these are rewritten by CLI args later)
SCALE = 1 / 90
SUBSAMPLING = 1
SIMPLIFY = 0.1 * SCALE
SIMPLIFYHQ = False
TRACEWIDTH = '0.1'

# Use Pythagoras to find the distance between two points
def dist(a, b):
    dx = a.real - b.real
    dy = a.imag - b.imag
    return math.sqrt(dx * dx + dy * dy)

# Parse a style tag into a dictionary
def styleParse(attr):
    out = dict()
    i = 0
    for tag in attr.split(';'):
            out[tag.split(':')[0]] = tag.split(':')[1]
            i += 1
    return out

# ray-casting algorithm based on
# http://www.ecse.rpi.edu/Homepages/wrf/Research/Short_Notes/pnpoly.html
def isInside(point, poly):
    x = point.real
    y = point.imag
    inside = False
    i = 0
    j = len(poly) - 1
    while i < len(poly):
        xi = poly[i].real
        yi = poly[i].imag
        xj = poly[j].real
        yj = poly[j].imag
        intersect = ((yi > y) != (yj > y)) and (x < ((xj - xi) * (y - yi) / (yj - yi) + xi))
        if intersect:
            inside = not inside
        j = i
        i += 1
    return inside


# Shoelace Formula without absolute value which returns negative if points are CCW
# https://stackoverflow.com/questions/14505565/detect-if-a-set-of-points-in-an-array-that-are-the-vertices-of-a-complex-polygon
def polygonArea(poly):
    area = 0
    i = 0
    while i < len(poly):
        j = (i + 1) % len(poly)
        area += poly[i].real * poly[j].imag
        area -= poly[j].real * poly[i].imag
        i += 1
    return area / 2


# Move a small distance away from path[idxa] towards path[idxb]
def interpPt(path, idxa, idxb):
    # a fraction of the trace width so we don't get much of a notch in the line

    amt = float(TRACEWIDTH) / 8

    # wrap index
    if idxb < 0:
        idxb += len(path)
    if idxb >= len(path):
        idxb -= len(path)
          
    # get 2 pts
    a = path[idxa]
    b = path[idxb]
    dx = b.real - a.real
    dy = b.imag - a.imag
    d = math.sqrt(dx * dx + dy * dy)
    if amt > d:
        return  # return nothing - will just end up using the last point
    return complex(a.real + (dx * amt / d), a.imag + (dy * amt / d))


# Some svg paths conatin multiple nested polygons. We need to open them and splice them together.
def unpackPoly(poly):
    # ensure all polys are the right way around
    if args.verbose:
        print('...Unpacking ' + str(len(poly)) + ' Polygons')
    p = 0
    while p < len(poly):
        if polygonArea(poly[p]) > 0:
            poly[p].reverse()
            if args.verbose:
                print('...Polygon #'+str(p)+' was backwards, reversed')
        p += 1

    # check for polys that are within more than 1 other poly,
    # extract them now, then we append them later
    # This isn't a perfect solution and only handles a single nesting
    extraPolys = []
    polyTmp    = []
    for j in range(len(poly)):
        c = 0
        for k in range(len(poly)):
            if j == k:
                continue
            if isInside(poly[j][0], poly[k]):
                c += 1
        if c > 1:
            extraPolys.append(poly[j])
        else:
            polyTmp.append(poly[j])

    poly = polyTmp
    finalPolys = [poly[0]]

    p = 1
    while p < len(poly):
        path = poly[p]
        outerPolyIndex = 'undefined'
        i = 0
        while i < len(finalPolys):
            if isInside(path[0], finalPolys[i]):
                outerPolyIndex = i
                break
            elif isInside(finalPolys[i][0], path):
                # polys in wrong order - old one is inside new one
                t = path
                path = finalPolys[i]
                finalPolys[i] = t
                outerPolyIndex = i
                break
            i += 1

        if outerPolyIndex != 'undefined':
            path.reverse()  # reverse poly
            outerPoly = finalPolys[outerPolyIndex]
            minDist = 10000000000
            minOuter = 0
            minPath = 0
            a = 0
            while a < len(outerPoly):
                b = 0
                while b < len(path):
                    l = dist(outerPoly[a], path[b])
                    if l < minDist:
                        minDist = l
                        minOuter = a
                        minPath = b
                    b += 1
                a += 1

                # splice the inner poly into the outer poly
                # but we have to recess the two joins a little
                # otherwise Eagle reports Invalid poly when filling
                # the top layer
            finalPolys[outerPolyIndex] = outerPoly[0:minOuter]
            stub = interpPt(outerPoly, minOuter, minOuter - 1)
            (finalPolys[outerPolyIndex].append(stub) if stub is not None else None)
            stub = interpPt(path, minPath, minPath + 1)
            (finalPolys[outerPolyIndex].append(stub) if stub is not None else None)
            finalPolys[outerPolyIndex].extend(path[minPath + 1:])
            finalPolys[outerPolyIndex].extend(path[:minPath])
            stub = interpPt(path, minPath, minPath - 1)
            (finalPolys[outerPolyIndex].append(stub) if stub is not None else None)
            stub = interpPt(outerPoly, minOuter, minOuter + 1)
            (finalPolys[outerPolyIndex].append(stub) if stub is not None else None)  
            finalPolys[outerPolyIndex].extend(outerPoly[minOuter + 1:])     
            
        else:
            # not inside, just add this poly
            finalPolys.append(path)

        p += 1

    #print(finalPolys)
    return finalPolys + extraPolys

#
#
# ******************************************************************************
#
#   Convert SVG paths to various EAGLE polygon formats
#
#
def drawSVG(svg_attributes, attributes, paths):

    global SCALE
    global SUBSAMPLING
    global SIMPLIFY
    global SIMPLIFYHQ
    global TRACEWIDTH

    out = ''
    svgWidth = 0
    svgHeight = 0

    if 'viewBox' in svg_attributes.keys():
        if svg_attributes['viewBox'].split()[2] != '0':
            svgWidth = str(
                round(float(svg_attributes['viewBox'].split()[2]), 2))
            svgHeight = str(
                round(float(svg_attributes['viewBox'].split()[3]), 2))
        else:
            svgWidth = svg_attributes['width']
            svgHeight = svg_attributes['height']
    else:
        svgWidth = svg_attributes['width']
        svgHeight = svg_attributes['height']

    specifiedWidth = svgWidth
    if 'mm' in specifiedWidth:
        specifiedWidth = float(specifiedWidth.replace('mm', ''))
        SCALE = specifiedWidth / float(svgWidth)
        if args.verbose:
            print("SVG width detected in mm \\o/")
    elif 'in' in specifiedWidth:
        specifiedWidth = float(specifiedWidth.replace('in', '')) * 25.4
        SCALE = specifiedWidth / float(svgWidth)
        if args.verbose:
            print("SVG width detected in inches")
    else:
        SCALE = (args.scaleFactor * 25.4) / 150
        if args.verbose:
            print("SVG width not found, guessing based on scale factor")


    exportHeight = float(svgHeight) * SCALE

    if args.outMode == "b":
        out += "CHANGE layer " + str(args.eagleLayerNumber) + \
            "; CHANGE rank 3; CHANGE pour solid; SET WIRE_BEND 2;\n"
    if args.outMode == "ls":
        out += "CHANGE layer " + str(args.eagleLayerNumber) + \
            "; CHANGE pour solid; Grid mm; SET WIRE_BEND 2;\n"
    if args.outMode == "ki":
        out += "(footprint \"buzzardLabel\"\n" + \
            " (layer \"F.Cu\")\n" + \
            " (attr board_only exclude_from_pos_files exclude_from_bom)\n"
    if args.outMode == "ki5":
        out += "(module \"buzzardLabel\"" + \
            " (layer \"F.Cu\")" + \
            " (tedit \"" + hex(int(time.time()))[2:-1].upper() + "\")\n" + \
            " (attr virtual)\n"


    if len(paths) == 0:
        print("No paths found. Did you use 'Object to path' in Inkscape?")
    anyVisiblePaths = False

    i = 0
    while i < len(paths):

        if args.verbose:
            print('Translating Path ' + str(i+1) + ' of ' + str(len(paths)))

        # Apply the tranform from this svg object to actually transform the points
        # We need the Matrix object from svgelements but we can only matrix multiply with
        # svgelements' version of the Path object so we're gonna do some dumb stuff
        # to launder the Path object from svgpathtools through a d-string into 
        # svgelements' version of Path. Luckily, the Path object from svgelements has 
        # backwards compatible .point methods
        pathTransform = Matrix('')
        if 'transform' in attributes[i].keys():
            pathTransform = Matrix(attributes[i]['transform'])
            if args.verbose:
                print('...Applying Transforms')
        path = elPath(paths[i].d()) * pathTransform
        path = elPath(path.d())

        # Another stage of transforms that gets applied to all paths
        # in order to shift the label around the origin

        tx = {
            'l':0,
            'c':0-(float(svgWidth)/2),
            'r':0-float(svgWidth)
        }
        ty = {
            't':250,
            'c':150,
            'b':50
        }
        path = elPath(paths[i].d()) * Matrix.translate(tx[args.originPos[1]],ty[args.originPos[0]])
        path = elPath(path.d())

        style = 0

        if 'style' in attributes[i].keys():
            style = styleParse(attributes[i]['style'])

        if 'fill' in attributes[i].keys():
            filled = attributes[i]['fill'] != 'none' and attributes[i]['fill'] != ''
        elif 'style' in attributes[i].keys():
            filled = style['fill'] != 'none' and style['fill'] != ''
        else:
            filled = False

        if 'stroke' in attributes[i].keys():
            stroked = attributes[i]['stroke'] != 'none' and attributes[i]['stroke'] != ''
        elif 'style' in attributes[i].keys():
            stroked = style['stroke'] != 'none' and style['stroke'] != ''
        else:
            stroked = False

        if not filled and not stroked:
            i += 1
            continue  # not drawable (clip path?)

        SUBSAMPLING = args.subSampling
        TRACEWIDTH = str(args.traceWidth)
        anyVisiblePaths = True
        l = path.length()
        divs = round(l * SUBSAMPLING)
        if divs < 3:
            divs = 3
        maxLen = l * 2 * SCALE / divs
        p = path.point(0)
        p = complex(p.real * SCALE, p.imag * SCALE)
        last = p
        polys = []
        points = []
        s = 0
        while s <= divs:
            p = path.point(s * 1 / divs)
            p = complex(p.real * SCALE, p.imag * SCALE)
            if dist(p, last) > maxLen:
                if len(points) > 1:
                    points = simplify(points, SIMPLIFY, SIMPLIFYHQ)
                    polys.append(points)
                points = [p]
            else:
                points.append(p)

            last = p
            s += 1

        if len(points) > 1:
            points = simplify(points, SIMPLIFY, SIMPLIFYHQ)          
            polys.append(points)

        if filled:
            polys = unpackPoly(polys)

        for points in polys:

            if len(points) < 2:
                return
                
            scriptLine = ''
            if filled:
                points.append(points[0]) # re-add final point so we loop around

            if args.outMode != "lib":

                if args.outMode == "b":
                    scriptLine += "polygon " + args.signalName + " " + TRACEWIDTH + "mm "

                if args.outMode == "ls":
                    scriptLine += "polygon " + TRACEWIDTH + "mm "

                if args.outMode.find("ki") == -1:
                    for p in points:
                        precisionX = '{0:.2f}'.format(round(p.real, 6))
                        precisionY = '{0:.2f}'.format(round(exportHeight - p.imag, 6))
                        scriptLine += '(' + precisionX + 'mm ' + precisionY + 'mm) '

                    scriptLine += ';'

                elif args.outMode.find("ki") != -1:
                    scriptLine += " (fp_poly (pts"
                    for p in points:
                        precisionX = "{0:.2f}".format(round(p.real, 6))
                        precisionY = "{0:.2f}".format(round(p.imag - exportHeight, 6))
                        scriptLine += " (xy " + precisionX + " " + precisionY + ")"

                    if args.outMode == "ki":
                        scriptLine += ") (layer \"F.SilkS\") (width 0.01) (fill solid))\n"
                    elif args.outMode == "ki5":
                        scriptLine += ") (layer \"F.SilkS\") (width 0.01))\n"
            else:

                scriptLine += "<polygon width=\"" + TRACEWIDTH + "\" layer=\"" + str(args.eagleLayerNumber) + "\">\n"

                for p in points:
                    precisionX = '{0:.2f}'.format(round(p.real, 6))
                    precisionY = '{0:.2f}'.format(round(exportHeight - p.imag, 6))
                    scriptLine += "<vertex x=\"" + precisionX + "\" y=\"" + precisionY + "\"/>\n"

                scriptLine += "</polygon>"

            out += scriptLine + '\n'

        i += 1

    if not anyVisiblePaths:
        print("No paths with fills or strokes found.")

    if args.outMode.find("ki") != -1:
        out += ')\n'

    return out


def generate(imagePath):

    path_to_script = os.path.dirname(os.path.abspath(__file__))

    if args.stdout:
        paths, attributes, svg_attributes = svg2paths2(imagePath)
        try:
            print(drawSVG(svg_attributes, attributes, paths))
        except:
            print("Failed to output")
            sys.exit(0)  # quit Python


    elif args.outMode != 'lib':
        paths, attributes, svg_attributes = svg2paths2(imagePath)
        ext = '.scr' if args.outMode.find("ki") == -1 else ".kicad_mod"

        try:
            f = open(path_to_script + "/" + args.destination + ext, 'w')
            f.write(drawSVG(svg_attributes, attributes, paths))
            f.close

        except:
            print("Failed to create output script file")
            sys.exit(0)  # quit Python

    else:
        imagePaths = imagePath.split(",")
        scripts = []

        for imageFile in imagePaths:
            paths, attributes, svg_attributes = svg2paths2(imageFile)
            scripts.append(drawSVG(svg_attributes, attributes, paths)) 

        try:
            output_path = path_to_script + "/" + args.destination + ".lbr"
            
            labelStrings = []
            for string in imagePaths:
                labelStrings.append(os.path.basename(string))
            
            if args.writeMode == 'a':
                new_contents = appendLib(scripts, labelStrings, output_path)

                with open(output_path, 'w') as f:
                    f.write(new_contents)

            else:
                f = open(output_path, 'w')
                f.write(writeLib(scripts, labelStrings))
                f.close

        except:
            print("Failed to create output library file")
            sys.exit(0)  # quit Python       

def writeLib(scriptStrings, labelStrings):

    head = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<!DOCTYPE eagle SYSTEM \"eagle.dtd\">\n<eagle version=\"7.7.0\">\n<drawing>\n<settings>\n<setting alwaysvectorfont=\"no\"/>\n<setting verticaltext=\"up\"/>\n</settings>\n<grid distance=\"1\" unitdist=\"mm\" unit=\"mm\" style=\"lines\" multiple=\"1\" display=\"yes\" altdistance=\"0.1\" altunitdist=\"mm\" altunit=\"mm\"/>\n<layers>\n<layer number=\"1\" name=\"Top\" color=\"4\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"2\" name=\"Route2\" color=\"1\" fill=\"3\" visible=\"no\" active=\"yes\"/>\n<layer number=\"3\" name=\"Route3\" color=\"4\" fill=\"3\" visible=\"no\" active=\"yes\"/>\n<layer number=\"4\" name=\"Route4\" color=\"1\" fill=\"4\" visible=\"no\" active=\"yes\"/>\n<layer number=\"5\" name=\"Route5\" color=\"4\" fill=\"4\" visible=\"no\" active=\"yes\"/>\n<layer number=\"6\" name=\"Route6\" color=\"1\" fill=\"8\" visible=\"no\" active=\"yes\"/>\n<layer number=\"7\" name=\"Route7\" color=\"4\" fill=\"8\" visible=\"no\" active=\"yes\"/>\n<layer number=\"8\" name=\"Route8\" color=\"1\" fill=\"2\" visible=\"no\" active=\"yes\"/>\n<layer number=\"9\" name=\"Route9\" color=\"4\" fill=\"2\" visible=\"no\" active=\"yes\"/>\n<layer number=\"10\" name=\"Route10\" color=\"1\" fill=\"7\" visible=\"no\" active=\"yes\"/>\n<layer number=\"11\" name=\"Route11\" color=\"4\" fill=\"7\" visible=\"no\" active=\"yes\"/>\n<layer number=\"12\" name=\"Route12\" color=\"1\" fill=\"5\" visible=\"no\" active=\"yes\"/>\n<layer number=\"13\" name=\"Route13\" color=\"4\" fill=\"5\" visible=\"no\" active=\"yes\"/>\n<layer number=\"14\" name=\"Route14\" color=\"1\" fill=\"6\" visible=\"no\" active=\"yes\"/>\n<layer number=\"15\" name=\"Route15\" color=\"4\" fill=\"6\" visible=\"no\" active=\"yes\"/>\n<layer number=\"16\" name=\"Bottom\" color=\"1\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"17\" name=\"Pads\" color=\"2\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"18\" name=\"Vias\" color=\"2\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"19\" name=\"Unrouted\" color=\"6\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"20\" name=\"Dimension\" color=\"15\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"21\" name=\"tPlace\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"22\" name=\"bPlace\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"23\" name=\"tOrigins\" color=\"15\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"24\" name=\"bOrigins\" color=\"15\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"25\" name=\"tNames\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"26\" name=\"bNames\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"27\" name=\"tValues\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"28\" name=\"bValues\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"29\" name=\"tStop\" color=\"7\" fill=\"3\" visible=\"no\" active=\"yes\"/>\n<layer number=\"30\" name=\"bStop\" color=\"7\" fill=\"6\" visible=\"no\" active=\"yes\"/>\n<layer number=\"31\" name=\"tCream\" color=\"7\" fill=\"4\" visible=\"no\" active=\"yes\"/>\n<layer number=\"32\" name=\"bCream\" color=\"7\" fill=\"5\" visible=\"no\" active=\"yes\"/>\n<layer number=\"33\" name=\"tFinish\" color=\"6\" fill=\"3\" visible=\"no\" active=\"yes\"/>\n<layer number=\"34\" name=\"bFinish\" color=\"6\" fill=\"6\" visible=\"no\" active=\"yes\"/>\n<layer number=\"35\" name=\"tGlue\" color=\"7\" fill=\"4\" visible=\"no\" active=\"yes\"/>\n<layer number=\"36\" name=\"bGlue\" color=\"7\" fill=\"5\" visible=\"no\" active=\"yes\"/>\n<layer number=\"37\" name=\"tTest\" color=\"7\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"38\" name=\"bTest\" color=\"7\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"39\" name=\"tKeepout\" color=\"4\" fill=\"11\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"40\" name=\"bKeepout\" color=\"1\" fill=\"11\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"41\" name=\"tRestrict\" color=\"4\" fill=\"10\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"42\" name=\"bRestrict\" color=\"1\" fill=\"10\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"43\" name=\"vRestrict\" color=\"2\" fill=\"10\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"44\" name=\"Drills\" color=\"7\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"45\" name=\"Holes\" color=\"7\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"46\" name=\"Milling\" color=\"3\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"47\" name=\"Measures\" color=\"7\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"48\" name=\"Document\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"49\" name=\"Reference\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"51\" name=\"tDocu\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"52\" name=\"bDocu\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"90\" name=\"Modules\" color=\"5\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"91\" name=\"Nets\" color=\"2\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"92\" name=\"Busses\" color=\"1\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"93\" name=\"Pins\" color=\"2\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"94\" name=\"Symbols\" color=\"4\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"95\" name=\"Names\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"96\" name=\"Values\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"97\" name=\"Info\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"98\" name=\"Guide\" color=\"6\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n</layers>\n"
    tail = "</drawing>\n</eagle>\n"
    lbrFile = head + "<library>\n<packages>\n"
    serialNum = 0

    # Write Packages
    for i in range(len(scriptStrings)):
        lbrFile += "<package name=\"" + cleanName(labelStrings[i].upper()) + str(serialNum) +  "\">\n"
        lbrFile += scriptStrings[i]
        lbrFile += "</package>\n"
        serialNum += 1
    lbrFile += "</packages>\n<symbols>\n"

    serialNum = 0

    # Write Symbols
    for i in range(len(scriptStrings)):
        lbrFile += "<symbol name=\"" + cleanName(labelStrings[i].upper()) + str(serialNum) + "\">\n"
        lbrFile += "<text x=\"0\" y=\"0\" size=\"1.778\" layer=\"94\">" + cleanName(labelStrings[i]) + "</text>\n</symbol>\n"
        serialNum += 1
    lbrFile += "</symbols>\n<devicesets>\n"

    serialNum = 0

    # Write Devicesets
    for i in range(len(scriptStrings)):
        lbrFile += "<deviceset name=\"" + cleanName(labelStrings[i].upper()) + str(serialNum) + "\">\n"
        lbrFile += "<gates>\n<gate name=\"G$1\" symbol=\"" + cleanName(labelStrings[i].upper()) + str(serialNum) + "\" x=\"0\" y=\"0\"/>\n</gates>\n<devices>\n"
        lbrFile += "<device name=\"\" package=\"" + cleanName(labelStrings[i].upper()) + str(serialNum) + "\">\n<technologies>\n<technology name=\"\"/>\n</technologies>\n</device>\n</devices>\n</deviceset>\n"
        serialNum += 1

    lbrFile += "</devicesets>\n</library>\n"
    lbrFile += tail

    return lbrFile

def appendLib(scriptStrings, labelStrings, file):

    template = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<!DOCTYPE eagle SYSTEM \"eagle.dtd\">\n<eagle version=\"7.7.0\">\n<drawing>\n<settings>\n<setting alwaysvectorfont=\"no\"/>\n<setting verticaltext=\"up\"/>\n</settings>\n<grid distance=\"1\" unitdist=\"mm\" unit=\"mm\" style=\"lines\" multiple=\"1\" display=\"yes\" altdistance=\"0.1\" altunitdist=\"mm\" altunit=\"mm\"/>\n<layers>\n<layer number=\"1\" name=\"Top\" color=\"4\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"2\" name=\"Route2\" color=\"1\" fill=\"3\" visible=\"no\" active=\"yes\"/>\n<layer number=\"3\" name=\"Route3\" color=\"4\" fill=\"3\" visible=\"no\" active=\"yes\"/>\n<layer number=\"4\" name=\"Route4\" color=\"1\" fill=\"4\" visible=\"no\" active=\"yes\"/>\n<layer number=\"5\" name=\"Route5\" color=\"4\" fill=\"4\" visible=\"no\" active=\"yes\"/>\n<layer number=\"6\" name=\"Route6\" color=\"1\" fill=\"8\" visible=\"no\" active=\"yes\"/>\n<layer number=\"7\" name=\"Route7\" color=\"4\" fill=\"8\" visible=\"no\" active=\"yes\"/>\n<layer number=\"8\" name=\"Route8\" color=\"1\" fill=\"2\" visible=\"no\" active=\"yes\"/>\n<layer number=\"9\" name=\"Route9\" color=\"4\" fill=\"2\" visible=\"no\" active=\"yes\"/>\n<layer number=\"10\" name=\"Route10\" color=\"1\" fill=\"7\" visible=\"no\" active=\"yes\"/>\n<layer number=\"11\" name=\"Route11\" color=\"4\" fill=\"7\" visible=\"no\" active=\"yes\"/>\n<layer number=\"12\" name=\"Route12\" color=\"1\" fill=\"5\" visible=\"no\" active=\"yes\"/>\n<layer number=\"13\" name=\"Route13\" color=\"4\" fill=\"5\" visible=\"no\" active=\"yes\"/>\n<layer number=\"14\" name=\"Route14\" color=\"1\" fill=\"6\" visible=\"no\" active=\"yes\"/>\n<layer number=\"15\" name=\"Route15\" color=\"4\" fill=\"6\" visible=\"no\" active=\"yes\"/>\n<layer number=\"16\" name=\"Bottom\" color=\"1\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"17\" name=\"Pads\" color=\"2\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"18\" name=\"Vias\" color=\"2\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"19\" name=\"Unrouted\" color=\"6\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"20\" name=\"Dimension\" color=\"15\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"21\" name=\"tPlace\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"22\" name=\"bPlace\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"23\" name=\"tOrigins\" color=\"15\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"24\" name=\"bOrigins\" color=\"15\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"25\" name=\"tNames\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"26\" name=\"bNames\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"27\" name=\"tValues\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"28\" name=\"bValues\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"29\" name=\"tStop\" color=\"7\" fill=\"3\" visible=\"no\" active=\"yes\"/>\n<layer number=\"30\" name=\"bStop\" color=\"7\" fill=\"6\" visible=\"no\" active=\"yes\"/>\n<layer number=\"31\" name=\"tCream\" color=\"7\" fill=\"4\" visible=\"no\" active=\"yes\"/>\n<layer number=\"32\" name=\"bCream\" color=\"7\" fill=\"5\" visible=\"no\" active=\"yes\"/>\n<layer number=\"33\" name=\"tFinish\" color=\"6\" fill=\"3\" visible=\"no\" active=\"yes\"/>\n<layer number=\"34\" name=\"bFinish\" color=\"6\" fill=\"6\" visible=\"no\" active=\"yes\"/>\n<layer number=\"35\" name=\"tGlue\" color=\"7\" fill=\"4\" visible=\"no\" active=\"yes\"/>\n<layer number=\"36\" name=\"bGlue\" color=\"7\" fill=\"5\" visible=\"no\" active=\"yes\"/>\n<layer number=\"37\" name=\"tTest\" color=\"7\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"38\" name=\"bTest\" color=\"7\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"39\" name=\"tKeepout\" color=\"4\" fill=\"11\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"40\" name=\"bKeepout\" color=\"1\" fill=\"11\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"41\" name=\"tRestrict\" color=\"4\" fill=\"10\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"42\" name=\"bRestrict\" color=\"1\" fill=\"10\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"43\" name=\"vRestrict\" color=\"2\" fill=\"10\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"44\" name=\"Drills\" color=\"7\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"45\" name=\"Holes\" color=\"7\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"46\" name=\"Milling\" color=\"3\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"47\" name=\"Measures\" color=\"7\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"48\" name=\"Document\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"49\" name=\"Reference\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"51\" name=\"tDocu\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"52\" name=\"bDocu\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"90\" name=\"Modules\" color=\"5\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"91\" name=\"Nets\" color=\"2\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"92\" name=\"Busses\" color=\"1\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"93\" name=\"Pins\" color=\"2\" fill=\"1\" visible=\"no\" active=\"yes\"/>\n<layer number=\"94\" name=\"Symbols\" color=\"4\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"95\" name=\"Names\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"96\" name=\"Values\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"97\" name=\"Info\" color=\"7\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n<layer number=\"98\" name=\"Guide\" color=\"6\" fill=\"1\" visible=\"yes\" active=\"yes\"/>\n</layers>\n<library>\n<packages>\n</packages>\n<symbols>\n</symbols>\n<devicesets>\n</devicesets>\n</library>\n</drawing>\n</eagle>\n"
    # end_num_re = re.compile('[0-9]*$')
    end_num_re = re.compile('(?P<order>[0-9]+)')


    if os.path.exists(file):
        tree = XMLET.parse(file)
        root = tree.getroot()
    else:
        root = XMLET.fromstring(template)

    lastSerialNum = None
    
    # find out what serial number to use at the beginning
    symbols = next(root.iter('symbols'))
    for symbol in symbols:
        matches = end_num_re.search(symbol.attrib["name"])
        if matches != None:
            num = int(matches.group())

            if lastSerialNum == None:
                lastSerialNum = num + 1
            else:
                if num >= lastSerialNum:
                    lastSerialNum = num + 1
    
    if lastSerialNum == None:
        lastSerialNum = 0

    serialNum = lastSerialNum

    # Write Packages
    packages = next(root.iter('packages'))
    for i in range(len(scriptStrings)):
        element = XMLET.SubElement(packages, 'package')
        element.attrib = {"name" : cleanName(labelStrings[i].upper()) + str(serialNum)}
        subroot = XMLET.fromstring("<root>" + scriptStrings[i] + "</root>")
        for subelement in subroot:
            element.append(subelement)

        serialNum += 1

    serialNum = lastSerialNum

    # Write Symbols
    symbols = next(root.iter('symbols'))
    for i in range(len(scriptStrings)):
        element = XMLET.SubElement(symbols, 'symbol')
        element.attrib = {"name" : cleanName(labelStrings[i].upper()) + str(serialNum)}
        subroot = XMLET.fromstring("<root>" + "<text x=\"0\" y=\"0\" size=\"1.778\" layer=\"94\">" + cleanName(labelStrings[i]) + "</text>" + "</root>")
        for subelement in subroot:
            element.append(subelement)

        serialNum += 1

    serialNum = lastSerialNum

    # Write Devicesets
    devicesets = next(root.iter('devicesets'))
    for i in range(len(scriptStrings)):
        element = XMLET.SubElement(devicesets, 'deviceset')
        element.attrib = {"name" : cleanName(labelStrings[i].upper()) + str(serialNum)}
        subroot = XMLET.fromstring("<root>" + "<gates>\n<gate name=\"G$1\" symbol=\"" + cleanName(labelStrings[i].upper()) + str(serialNum) + "\" x=\"0\" y=\"0\"/>\n</gates>\n<devices>\n<device name=\"\" package=\"" + cleanName(labelStrings[i].upper()) + str(serialNum) + "\">\n<technologies>\n<technology name=\"\"/>\n</technologies>\n</device>\n</devices>\n" + "</root>")
        for subelement in subroot:
            # print(subelement)
            element.append(subelement)
        
        serialNum += 1

    # make sure there are newlines after every element
    # good solution from SO: https://stackoverflow.com/questions/3095434/inserting-newlines-in-xml-file-generated-via-xml-etree-elementtree-in-python/33956544#33956544
    def indent(elem, level=0):
        indent_string="" # you can choose various symbols / strings to indent with... use "" for no indentation
        i = "\n" + level*indent_string
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + indent_string
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                indent(elem, level+1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i
    
    indent(root)

    return "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<!DOCTYPE eagle SYSTEM \"eagle.dtd\">\n" + XMLET.tostring(root, encoding='unicode', method='xml')

def cleanName(name):

    name = name.replace(' ', '_')
    nonWords = re.compile('\W')
    name = nonWords.sub('#', name)

    return name
        
#
#
# ******************************************************************************
#
#   Python port of:
#   Simplify.js, a high-performance JS polyline simplification library
#   Vladimir Agafonkin, 2013
#   mourner.github.io/simplify-js
#

# square distance from a point to a segment
def getSqSegDist(p, p1, p2):

    x = p1.real
    y = p1.imag
    dx = p2.real - x
    dy = p2.imag - y

    if dx != 0 or dy != 0:

        t = ((p.real - x) * dx + (p.imag - y) * dy) / (dx * dx + dy * dy)

        if (t > 1):
            x = p2.real
            y = p2.imag

        elif (t > 0):
            x += dx * t
            y += dy * t

    dx = p.real - x
    dy = p.imag - y

    return dx * dx + dy * dy

# basic distance-based simplification
def simplifyRadialDist(points, sqTolerance):

    prevPoint = points[0]
    newPoints = [prevPoint]

    i = 1
    leng = len(points)

    while i < leng:
        point = points[i]

        if dist(point, prevPoint) > sqTolerance:
            newPoints.append(point)
            prevPoint = point

        i += 1

    if prevPoint != point:
        newPoints.append(point)

    return newPoints

# simplification using optimized Douglas-Peucker algorithm with recursion elimination
def simplifyDouglasPeucker(points, sqTolerance):

    leng = len(points)
    markers = [''] * leng
    first = 0
    last = leng - 1
    stack = []
    newPoints = []

    markers[first] = markers[last] = 1

    while last:

        maxSqDist = 0

        i = first + 1
        while i < last:
            sqDist = getSqSegDist(points[i], points[first], points[last])

            if sqDist > maxSqDist:
                index = i
                maxSqDist = sqDist

            i += 1

        if maxSqDist > sqTolerance:
            markers[index] = 1
            stack.extend([first, index, index, last])

        if stack:
            last = stack.pop()
            first = stack.pop()
        else:
            break

    i = 0
    while i < leng:
        if markers[i]:
            newPoints.append(points[i])
        i += 1

    return newPoints

# both algorithms combined for awesome performance
def simplify(points, tolerance, highestQuality):

    sqTolerance = tolerance * tolerance if tolerance != '' else 1

    points = points if highestQuality else simplifyRadialDist(
        points, sqTolerance)

    points = simplifyDouglasPeucker(points, sqTolerance)

    return points
#
#
# ******************************************************************************
#
#   Main program flow
#

if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='SparkFun Buzzard Label Generator')

    parser.add_argument('imageFile', help='Path to target image file')

    parser.add_argument('-s', dest='scaleFactor', default=0.04,
                        type=float, help='Text Height in inches (same as EAGLE text size value)')

    parser.add_argument('-l', dest='eagleLayerNumber', default=21,
                        type=int, help='Layer in EAGLE to create label into (default is tPlace layer 21)')

    parser.add_argument('-v', dest='verbose', default=False,
                        help='Verbose mode (helpful for debugging)', action='store_true')

    parser.add_argument('-o', dest='outMode', default='b', choices=['b', 'ls', 'lib', 'ki', 'ki5'],
                        help='Output Mode (\'b\'=board script, \'ls\'=library script, \'lib\'=library file, \'ki\'=KiCad v6 footprint, \'ki5\'=KiCad v5 footprint)')

    parser.add_argument('-n', dest='signalName', default='GND',
                        help='Signal name for polygon. Required if layer is not 21 (default is \'GND\')')
    
    parser.add_argument('-u', dest='subSampling', default=0.1,
                        type=float, help='Subsampling Rate (larger values provide smoother curves with more points)')  

    parser.add_argument('-t', dest='traceWidth', default=0.01,
                        type=float, help='Trace width in mm') 

    parser.add_argument('-a', dest='originPos', default='cl', choices=['tl', 'cl', 'bl', 'tc', 'cc', 'bc', 'tr', 'cr', 'br'],
                        help='Footprint anchor position (default:cl)')

    parser.add_argument('-w', dest='writeMode', default='w', choices=['w', 'a'],
                        help='Output writing mode (default:w)')

    parser.add_argument('-d', dest='destination', default='output',
                    help='Output destination filename (extension depends on -o flag)')

    parser.add_argument('-stdout', dest='stdout', default=False, action='store_true',
                    help='If Specified output is written to stdout')                    

    args = parser.parse_args()
          
    generate(args.imageFile)

    #
    # ******************************************************************************
