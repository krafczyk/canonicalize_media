#!/bin/bash
dotnet PgsToSrt/src/out/PgsToSrt.dll --tesseractdata /usr/share/tessdata --tesseractversion 5 --libleptname leptonica --libleptversion 6 --input $@
