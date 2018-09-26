import argparse
import json
import math

LINE_PROXIMITY_TOLERANCE = 5
JUSTIFICATION_TOLERANCE = 8

def bbTop(bbox):
    #Return the top of the bounding box
    return((bbox[1]+bbox[3])/2 )
    
def bbBottom(bbox):
    #Return the bottom of the boundng box
    return((bbox[5]+bbox[7])/2 )

def isJustified(bbox1, bbox2):
    #Check if bounding boxes are left or right justified
    if abs( ((bbox1[0] + bbox1[6])/2) - ((bbox2[0] + bbox2[6])/2) ) <= JUSTIFICATION_TOLERANCE:
        return(True) # left justified
    #
    if abs( ((bbox1[2] + bbox1[4])/2) - ((bbox2[2] + bbox2[4])/2) ) <= JUSTIFICATION_TOLERANCE:
        return(True) # right justified
    else:
        return(False) 

def lineMatch(bbox1, bbox2):
    # check if bottom and top of lines are close enough to be part of a text block
    if (abs(bbBottom(bbox1) - bbTop(bbox2) ) <= LINE_PROXIMITY_TOLERANCE ) and isJustified(bbox1, bbox2):
        return(True)
    else:
        return(False)
    

if(__name__ == '__main__'):
    parser = argparse.ArgumentParser(description=
        'parse a json file from Azure Cognitive Services OCR to identify text blocks')
    parser.add_argument('-f', '--file', metavar='file', nargs=1,
        help='file with the json data from Cognitive services OCR', required=True)
    parser.add_argument('-D', '--debug',
            help="Run script in debug mode", action="store_true")

    args = parser.parse_args()
    jfile = "d:\\Users\\djb\\Cloud\\Microsoft\\OneDrive - Microsoft\\DOH\\BSA\\PrescriptionServices\\src\\textBlockScan\\" + args.file[0].strip()


    with open(jfile) as f:
        ocr_resp = json.load(f)  


    if 'failed' in ocr_resp.keys() and ocr_resp['failed'] == False:
        if 'recognitionResult' in  ocr_resp.keys():
            # empty list to put the text blocks in 
            # list of list of lines
            textBlocks = []
            for lidx, l_rec in enumerate(ocr_resp['recognitionResult']['lines']):
                # check each line with others to see if there is a top/bottom
                # & justification match                
                for midx, m_rec in enumerate(ocr_resp['recognitionResult']['lines']):
                    if (midx != lidx):
                        # we don't want to match ourselves

                        # check if lower is within LINE_PROXIMITY_TOLERANCE 
                        #  of next line upper and we have L or R justification
                        if( lineMatch(l_rec['boundingBox'] , m_rec['boundingBox'])):
                            # if we have a match add to existing 
                            # text block list or create a new one
                            eitherLineFound = False
                            for tbtidx in range(0,len(textBlocks)):
                                if lidx in textBlocks[tbtidx]  and midx not in textBlocks[tbtidx]:
                                    textBlocks[tbtidx].append(midx)
                                    eitherLineFound = True
                                if midx in textBlocks[tbtidx]  and lidx not in textBlocks[tbtidx]:
                                    textBlocks[tbtidx].append(lidx)
                                    eitherLineFound = True
                            # if we pass thru loop testing each list and don't find either line 
                            # add as new list
                            if eitherLineFound == False:
                                textBlocks.append([lidx,midx])
                        # We can still have lines that don't match any others
                        # we need to add them later
                       
            for slNo in range(0, len(ocr_resp['recognitionResult']['lines']) ):
                lnInTblk = False
                for tBlck in textBlocks:
                    if slNo in tBlck:
                        lnInTblk = True                
                if lnInTblk == False:
                    textBlocks.append([slNo,])

            # array of text block arrays of text lines
            tbArray = []
            for tb in textBlocks:
                tBlck = []
                for ln in tb:
                    lineDir = {'lineNo' : ln, 'lineTxt': ocr_resp['recognitionResult']['lines'][ln]['text'] }
                    tBlck.append(lineDir)
                    print(ocr_resp['recognitionResult']['lines'][ln]['text'])

                tbArray.append(tBlck)

    print(json.dumps(tbArray, indent=4, separators=(',', ': ')) )
    print("Script ends")    