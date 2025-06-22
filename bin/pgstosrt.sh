#!/bin/bash
dotnet PgsToSrt/PgsToSrt.dll --tesseractdata /usr/share/tessdata --tesseractversion 5 --libleptname leptonica --libleptversion 6 --input "$1"
