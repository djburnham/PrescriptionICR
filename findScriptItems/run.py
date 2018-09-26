from __future__ import print_function
from pydocumentdb import document_client
import os
import json
import sys
import requests
import ConfigParser
from pprint import pprint as pp

__author__ = 'David.Burnham@microsoft.com'

def bbTop(bbox):
    #Return the top of the bounding box
    return((bbox[1]+bbox[3])/2 )
    
def bbBottom(bbox):
    #Return the bottom of the boundng box
    return((bbox[5]+bbox[7])/2 )

def isJustified(bbox1, bbox2):
    #Check if bounding boxes are left or right justified
    if abs( ((bbox1[0] + bbox1[6])/2) - ((bbox2[0] + bbox2[6])/2) ) <= _JUSTIFICATION_TOLERANCE:
        return(True) # left justified
    #
    if abs( ((bbox1[2] + bbox1[4])/2) - ((bbox2[2] + bbox2[4])/2) ) <= _JUSTIFICATION_TOLERANCE:
        return(True) # right justified
    else:
        return(False) 

def lineMatch(bbox1, bbox2):
    # check if bottom and top of lines are close enough to be part of a text block
    if (abs(bbBottom(bbox1) - bbTop(bbox2) ) <= _LINE_PROXIMITY_TOLERANCE ) and isJustified(bbox1, bbox2):
        return(True)
    else:
        return(False)
    
def write_http_response(status, body_dict):
    # Format and write out an http response  
    return_dict = {
        "status": status,
        "body": body_dict,
        "headers": {
            "Content-Type": "application/json"
        }
    }
    output = open(os.environ[_AZURE_FUNCTION_HTTP_OUTPUT_ENV_NAME], 'w')
    output.write(json.dumps(return_dict))
    output.close()

def textBlockScan(postdict):
    """ Scans the output of the OCR cognitive service and puts the lines of text
        into blocks by their placement and justification """
    textBlocks = []
    for lidx, l_rec in enumerate(postdict['recognitionResult']['lines']):
        # check each line with others to see if there is a top/bottom
        # & justification match                
        for midx, m_rec in enumerate(postdict['recognitionResult']['lines']):
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
    # print(textBlocks)                
    # We can still have lines that don't match any others
    #  -we need to add them 
    for slNo in range(0, len(postdict['recognitionResult']['lines']) ):
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
                lineDir = {'lineNo' : ln, 'lineTxt': postdict['recognitionResult']['lines'][ln]['text'] }
                tBlck.append(lineDir)
                print(postdict['recognitionResult']['lines'][ln]['text'])
                    # 
        tbArray.append(tBlck)
    #
    return(tbArray)

if __name__ == '__main__':

    #Get the configuration variables for the run
    config = ConfigParser.ConfigParser()
    config.read('findScriptItems/config.ini')

    LUIS_URL = config.get('FINDSCRIPTITEMS', 'LUIS_URL')
    SUB_KEY = config.get('FINDSCRIPTITEMS', 'SUB_KEY')
    LUIS_MATCH_SCORE_MIN = config.getfloat('FINDSCRIPTITEMS', 'LUIS_MATCH_SCORE_MIN')

    CdbURI = config.get('FINDSCRIPTITEMS', 'CdbURI')
    CdbKey = config.get('FINDSCRIPTITEMS', 'CdbKey')
    CdbID = config.get('FINDSCRIPTITEMS', 'CdbID')
    CdbCollID = config.get('FINDSCRIPTITEMS', 'CdbCollID')
    # these should also go into the config file
    _AZURE_FUNCTION_DEFAULT_METHOD = "POST"
    _AZURE_FUNCTION_HTTP_INPUT_ENV_NAME = "req"
    _AZURE_FUNCTION_HTTP_OUTPUT_ENV_NAME = "res"
    _REQ_PREFIX = "REQ_"
    _LINE_PROXIMITY_TOLERANCE = 5
    _JUSTIFICATION_TOLERANCE = 8

    
    print("Started processing the OCR Data")
    env = os.environ

    # Get HTTP METHOD
    http_method = env['REQ_METHOD'] if 'REQ_METHOD' in env else _AZURE_FUNCTION_DEFAULT_METHOD
    print("HTTP METHOD => {}".format(http_method))

    if http_method.lower() == 'post':
        request_body = open(env[_AZURE_FUNCTION_HTTP_INPUT_ENV_NAME], "r").read()
        print("Got request body as Text")
    else:
        resp = {"message" : "need to call this service with POST method to be useful."}
        write_http_response(200, resp )
        exit(0)

    # get request_body as a dictionary
    try:
        postdict = json.loads(request_body)
    except ValueError as e:
        erresp = {"errmsg" : "Could not deserialise posted body - is it valid json?"}      
        write_http_response(400, erresp )
        exit(0)

    if ( 'recognitionResult' not in postdict.keys()
    and 'succeeded' not in postdict.keys()):
        erresp = {"errmsg" : "recognitionResult and succeeded values not found in posted body json"}
        write_http_response(400, erresp )
        exit(0)
    #
    # now we call textBlockScan to get an array of textBlocks back by placement
    tbArray = textBlockScan(postdict)

    write_http_response(200, tbArray)