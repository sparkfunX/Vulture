# SparkFun Vulture SVG Import Tool

The Vulture Tool is designed to process vector graphics files into device footprints for EAGLE or KiCAD. 

## Preparing Vector Graphics for Vulture

Most vector graphics files are not compatible with Vulture "out-of-the-box" but they can be pre-processed quickly and easily. We 
recommend using the free, open-source software [Inkscape](https://inkscape.org/) although any vector graphics editor should work
fine. Below, we've outlined a basic protocol for pre-processing vector image files in Inkscape.

### Step 1) Open your image file in Inkscape

Open the InkScape software and then open your vector image

![opening an image in inkscape](/documentation/pp1.PNG)

### Step 2) Flatten and convert all shapes to paths

Vulture can only "see" paths, so we need to make sure that every shape in the document is defined as a path. 

Select All objects (press Ctrl + A) and then run `Path>Object to Path` (press Shift+Ctrl+C)

![highlighting object to path tool](/documentation/pp2.PNG)

You may need to repeat this a few times to catch all objects in the document. There's no harm in doing it 3 or 4 times just in case.

### Step 3) Ensure all paths have fill/stroke

Any paths that don't have a defined fill and/or stroke color will be ignored by the Vulture tool. In most cases, you'll want all paths 
to be visible to Vulture. Start by selecting all paths again (Ctrl + A) and run `Object>Fill and Stroke` (Shift + Ctrl + F)

![highlighting the fill and stroke tool](/documentation/pp3.PNG)

![highlighting solid color fill option](/documentation/pp4.PNG)

![highlighting no paint stroke option](/documentation/pp5.PNG)

### Step 4) Set drawing units to real units (mm/cm/in)

The Vulture tool is designed to import vector images at 1:1 scale. In order to do that, we require images to have absolute units such as cm/mm/inch. 
Millimeters are the native unit for Vulture but inches and centimeters are converted. Open the Document Properties dialog (Shift + Ctrl + D) 

![highlighting document properties option](/documentation/pp6.PNG)

Find the `Display Units` and `Units` fields and set them to your preferred units

![highlighting units fields in document properties](/documentation/pp7.PNG)

### Step 5) Save as a Plain .SVG file

Save your pre-processed image file as "Plain SVG" format to ensure that all of the expected attribute tags are present.

![highlighting Plain SVG in the Save As dialog](/documentation/pp8.PNG)

Your file should now be ready to convert using Vulture.

```
usage: vulture.py [-h] [-s SCALEFACTOR] [-l EAGLELAYERNUMBER] [-v]
                  [-o {b,ls,lib,ki,ki5}] [-n SIGNALNAME] [-u SUBSAMPLING]
                  [-t TRACEWIDTH] [-a {tl,cl,bl,tc,cc,bc,tr,cr,br}] [-w {w,a}]
                  [-d DESTINATION] [-stdout]
                  imageFile

SparkFun Buzzard Label Generator

positional arguments:
  imageFile             Path to target image file (.svg)

optional arguments:
  -h, --help            show this help message and exit
  -s SCALEFACTOR        Factor by which to scale the size of the imported
                        image (default: 1)
  -l EAGLELAYERNUMBER   Layer in EAGLE to create label into (default is tPlace
                        layer 21)
  -v                    Verbose mode (helpful for debugging)
  -o {b,ls,lib,ki,ki5}  Output Mode ('b'=board script, 'ls'=library script,
                        'lib'=library file, 'ki'=KiCad v6 footprint,
                        'ki5'=KiCad v5 footprint)
  -n SIGNALNAME         Signal name for polygon. Required if layer is not 21
                        (default is 'GND')
  -u SUBSAMPLING        Subsampling Rate, if the imported image is "jagged"
                        try a larger number here (larger values provide
                        smoother curves with more points. default: 5)
  -t TRACEWIDTH         Trace width in mm
  -a {tl,cl,bl,tc,cc,bc,tr,cr,br}
                        Footprint anchor position (default:cl)
  -w {w,a}              Output writing mode (default:w)
  -d DESTINATION        Output destination filename (extension depends on -o
                        flag)
  -stdout               If Specified output is written to stdout

```

  ## SCALEFACTOR
  
  This argument controls the output size of the image. This is a `float` by which the dimensions of the image are multiplied
  
  ## EAGLELAYERNUMBER
  
  This argument controls which EAGLE layer the tag is written to. Default value is 21 (tPlace)

  ## Verbose Mode
  
  If something gets borked, try running again with `-v` to see what's happening under the hood
  
  ## Output Mode
  
  This argument controls which format the tag output is generated for
  
  ### Board Script Mode
  
  By default, buzzard.py will generate a file called `output.scr` which can be run in the EAGLE board editor.
  
  ### Library Script Mode
  
  Library script mode will generate a file called `output.scr` which can be run in the EAGLE library footprint editor.
  
  ### Library Package Mode
  
  Library package mode will generate a file called `output.lbr` which is an EAGLE library file containing the specified image/images

  ### KiCad Footprint Mode

  KiCad footprint mode will generate a file called 'output.kicad_mod' which is a KiCad footprint file containing the specified image
  
  ## SIGNALNAME
  
  This argument defines the EAGLE signal name of the output, which is only required for metal layers. It is `GND` by default.
  
  ## SUBSAMPLING
  
  This argument essentially defines the resolution of the output. A larger number will produce smoother curves but larger files. 
  **Note:**  If your output image looks "jagged" or "low-res" then try a larger number here
  
  ## TRACEWIDTH

  Tracewidth of output in mm
  
  ## Anchor Position
  
  In library package output mode, the position of the anchor point can be specified using the `-a` argument. The default value is `cl`
  The following values are permissible:
  
  ```
  tl - top left
  cl - center left
  bl - bottom left
  tc - top center
  cc - center center
  bc - bottom center
  tr - top right
  cr - center right
  br - bottom right
  ```
  
  ## Output Writing Mode

  By default, buzzard.py with overwrite the output file. Running with the `-w a` option, however, will run buzzard.py in "append mode," 
  adding the specified tag to the existing output file.
  
  ## Destination Filename
  
  Using the `-d` flag will allow you to specify the name of the output file. The file extension will automatically be selected based on
  the output format.

  ## STDOUT Print Mode

  If this argument is specified, the output will be written to stdout instead of a file. This is handy for piping to clipboard, etc.
  
