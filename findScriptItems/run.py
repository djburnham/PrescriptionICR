from __future__ import print_function
from pydocumentdb import document_client
import os
import json
import sys
import requests
import ConfigParser
import copy
import difflib
from pprint import pprint as pp

__author__ = 'David.Burnham@microsoft.com'

def bbTop(bbox):
    """Return the top of the bounding box"""
    return((bbox[1]+bbox[3])/2 )
    
def bbBottom(bbox):
    """Return the bottom of the boundng box"""
    return((bbox[5]+bbox[7])/2 )

def isJustified(bbox1, bbox2):
    """Check if bounding boxes are left or right justified"""
    if ( abs( ((bbox1[0] + bbox1[6])/2) - ((bbox2[0] + bbox2[6])/2) ) 
    <= _JUSTIFICATION_TOLERANCE):
        return(True) # left justified
    #
    if ( abs( ((bbox1[2] + bbox1[4])/2) - ((bbox2[2] + bbox2[4])/2) )
       <= _JUSTIFICATION_TOLERANCE):
        return(True) # right justified
    else:
        return(False) 

def lineMatch(bbox1, bbox2):
    """ check if bottom and top of lines are close enough 
        to be part of a text block"""
    if ( (abs(bbBottom(bbox1) - bbTop(bbox2) ) <= _LINE_PROXIMITY_TOLERANCE )
       and isJustified(bbox1, bbox2) ):
        return(True)
    else:
        return(False)
    
def write_http_response(status, body_dict):
    """Format and write out an http response  """
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
                # 
        tbArray.append(tBlck)
    #
    return(tbArray)

def lookupMedProd(medProdStr):
    """check the medical products store in CosmosDB for the product
    Todo:
        There is almost no error handling - what if the network
            database is not available?
    """
    query = {'query': """SELECT * FROM prescriptionItems p 
     WHERE CONTAINS( p.MEDICINAL_PRODUCT_NAME, '{0}' )""".format(medProdStr)}
    
    docs = CdbClient.QueryDocuments(coll_link, query)
    resLst = list(docs)
    resDict = dict()
    if len(resLst) == 1:
        resDict['search'] = 'oneFound'
        resDict['medical_product_name'] = resLst[0][u'MEDICINAL_PRODUCT_NAME']
        resDict['product_id'] = resLst[0][u'id']
        return resDict
    else:        
        # chop string in half and search - likely to get a set of results
        # use difflib to select the most similar to the search string
        halfStr = medProdStr[0:int(len(medProdStr)/2)]
        query = {'query': """SELECT p.id, p.MEDICINAL_PRODUCT_NAME 
         FROM prescriptionItems p
         WHERE CONTAINS( p.MEDICINAL_PRODUCT_NAME, '{0}' )""".format(halfStr)}
        docs = CdbClient.QueryDocuments(coll_link, query)
        matchLst = list(docs)
        bestMatchMedProdName = ''
        bestMatchMedProdID = 0
        bestMatchValue = 0
        if len(matchLst) > 0 and u'MEDICINAL_PRODUCT_NAME' in matchLst[0].keys():
            for matchLineDict in matchLst:
                matchVal = difflib.SequenceMatcher(None, medProdStr, 
                 matchLineDict[u'MEDICINAL_PRODUCT_NAME'] ).ratio()
                if matchVal > bestMatchValue :
                     bestMatchMedProdName = matchLineDict[u'MEDICINAL_PRODUCT_NAME']
                     bestMatchMedProdID = matchLineDict[u'id']
                     bestMatchValue = matchVal
            
            resDict['search'] = 'matchedFromFirstHalf'
            resDict['medical_product_name'] = bestMatchMedProdName
            resDict['product_id'] = bestMatchMedProdID
            return resDict
        else:
            resDict['search'] = 'noMatch'
            return resDict


def makeLUIScall(line):
    """make a call to the LUIS service to see Line intent
    """
    try:
        r = requests.get(LUIS_URL, params={'subscription-key': SUB_KEY, 'q': line})
    except requests.exceptions.RequestException as e:  # This is the correct syntax
        print(e)
        sys.exit(1)
    if r.status_code == 200:
        resDir = json.loads(r.text)
        if float(resDir['topScoringIntent']['score']) > LUIS_MATCH_SCORE_MIN:
            resDir['result'] = 'success'
            return resDir
        else:
            resDir['result'] = 'inconclusive'
            return resDir
    else:
        resDir = dict()
        resDir['result'] = 'callFailed'
        return resDir

def toInt(inStr):
    """ return an integer from a text string or word """
    inStr = inStr.encode('ascii','ignore')
    inStr = inStr.strip().lower()
    convDict = {
                    'one':1,
                    'two':2,
                    'three':3,
                    'four':4,
                    'five':5,
                    'six':6,
                    'seven':7,
                    'eight':8,
                    'nine':9,
                    'ten':10,
                    '1':1,
                    '2':2,
                    '3':3,
                    '4':4,
                    '5':5,
                    '6':6,
                    '7':7,
                    '8':8,
                    '9':9,
                    '10':10 }

    if inStr not in convDict.keys():
        return 0
    else:
        return convDict[inStr]               

def lineInSameBlockAsLineList(lineNo, lineList):
    """ Function to see if lineNo is in a textBlock that also contains 
    any of the lines in the list containined in lineList """
    lineListInBlock = []
    for textBlock in tbArray:
        for textLine in textBlock:
            # get line numbers in the block
            lineListInBlock.append(textLine['lineNo'])
        if lineNo in lineListInBlock:
            # this is the block we're interested in 
            for testLine in lineList:
                if testLine in lineListInBlock:
                    return True
                else:
                    return False

        lineListInBlock = []
    return False



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

    LUIScalls = 0

    # prescription items identified 
    prescriptionItms = {}
    # list of identified prescription items
    prescriptionItmsLst = [] 

    # set up access to the Cosmos DB instance
        # set up a connection to CosmsoDB
    CdbClient = document_client.DocumentClient(CdbURI, {'masterKey': CdbKey})
    # get the db identifier
    db_query = "select * from r where r.id = '{0}'".format(CdbID)
    db = list(CdbClient.QueryDatabases(db_query))[0]
    db_link = db['_self']
    # get the collections ID
    coll_id = CdbCollID
    coll_query = "select * from r where r.id = '{0}'".format(coll_id)
    collLst = list(CdbClient.QueryCollections(db_link, coll_query))
    if len(collLst) == 1:
        coll = list(CdbClient.QueryCollections(db_link, coll_query))[0]
    else:
        print("Error - are you sure you have the collection name correct?")
    coll_link = coll['_self']

    print("Started processing the OCR Data")
    env = os.environ

    # Get HTTP METHOD
    http_method = env['REQ_METHOD'] if 'REQ_METHOD' in env else _AZURE_FUNCTION_DEFAULT_METHOD

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
    # we iterate over tbArray calling LuiS model on each line and adding the intent to the tbArray
    for textBlock in tbArray:
        for textLine in textBlock:
            # each line in a block
            LUISres = makeLUIScall(textLine['lineTxt'])
            LUIScalls = LUIScalls + 1
            if LUISres['result'] == 'success':
                textLine['LUISres'] = LUISres['topScoringIntent']['intent']
                textLine['LUISscore'] = LUISres['topScoringIntent']['score']

                if ( LUISres['topScoringIntent']['intent'] == 
                    'prescriptionItemNumber'):
                    # need to get the number of items on the prescription if
                    # intent is detected and find entity in the returned LUISres
                    if ( (len(LUISres['entities']) == 1 ) 
                    and LUISres['entities'][0]['type'] == "noItem"):
                        noPresItemChk = toInt(LUISres['entities'][0]['entity'])
                        print("Expect to find {} items in script".format(noPresItemChk))

                if ( LUISres['topScoringIntent']['intent'] == 
                    'medicinalProductName'):
                    # We are relying on the LUIS model finding the med product
                    # Should we also test none intent also ?

                    # see if we can find the medical product in the database
                    lookUpDict = lookupMedProd(textLine['lineTxt'])
                    if lookUpDict['search'] == 'oneFound':
                        textLine['MedProdName'] = lookUpDict['medical_product_name']
                        textLine['MedProdID'] = int(lookUpDict['product_id'])
                        textLine['MedProdMatch'] = 'exact'
                    # handle best match searches    
                    elif lookUpDict['search'] == 'matchedFromFirstHalf':
                        textLine['MedProdName'] = lookUpDict['medical_product_name']
                        textLine['MedProdID'] = int(lookUpDict['product_id'])
                        textLine['MedProdMatch'] = 'bestMatch'

            else:
                textLine['LUISres'] = 'undetermined'

    # We will try and identify blocks having medical products and quantities 
    # from the augmented textBlocks

    medProdProcessedLineNos = [] #List containing product line# we've processed
    for textBlock in tbArray:
        # find text blocks that have MedProdName, directions and quantity
        mpname = 0
        direct = 0
        quantity = 0
        for textLine in textBlock:
            if 'MedProdName' in textLine.keys():
                mpname += 1
                medProdToAdd = (textLine['MedProdName'], textLine['MedProdID'], textLine['lineNo'])

            if textLine['LUISres'] == u'directions':
                direct += 1

            if textLine['LUISres'] == u'quantity':
                quantity += 1
                quantityToAdd = textLine['lineTxt']

        if mpname == 1 and direct == 1 and quantity == 1:
            prescriptionItms['MedProdName'] = medProdToAdd[0]
            prescriptionItms['MedProdID'] = medProdToAdd[1]
            prescriptionItms['Quantity'] = quantityToAdd
            prescriptionItms['IDType'] = 'Colocated MDQ'
            prescriptionItmsLst.append(copy.deepcopy(prescriptionItms))
            medProdProcessedLineNos.append(copy.deepcopy(medProdToAdd[2]))

    # find text blocks that have MedProdName, directions and quantity in 
    # adjacent blocks but excluding any blocks with MDQ identified already
    orphanedMedProd = ()
    orphanedDirections = 0
    orphanedQuantity = u''
    for textBlock in tbArray:

        if lineInSameBlockAsLineList(textBlock[0]['lineNo'],
         medProdProcessedLineNos ):
            continue
        elif len(orphanedMedProd) == 0:
            # go thru lines in block to see if we can find an orphaned product
            for textLine in textBlock:
                if ( u'MedProdName' in textLine.keys() and textLine['lineNo'] 
                 not in medProdProcessedLineNos ):
                    orphanedMedProd = ( textLine['MedProdName'], 
                     textLine['MedProdID'], textLine['lineNo'])

                if ( textLine['LUISres'] == u'directions' and
                 orphanedMedProd is not None ):
                    # only if this happens after we've found  medical prod
                    orphanedDirections += 1

                if ( textLine['LUISres'] == u'quantity' and
                 orphanedMedProd is not None ):
                    # only if this happens after we've found  medical prod
                    orphanedQuantity = textLine['lineTxt']

        elif len(orphanedMedProd) != 0:
            # we have an orphan medical product set from last block
            # see if we can find directions and quantity in the next block
            for textLine in textBlock:

                if ( textLine['LUISres'] == u'directions' 
                 and orphanedDirections == 0):
                    orphanedDirections += 1

                if ( textLine['LUISres'] == u'quantity' and
                 orphanedQuantity == u''):
                    orphanedQuantity = textLine['lineTxt']
            
            if ( len(orphanedMedProd) != 0 and orphanedDirections > 0 and
             orphanedQuantity != u''):
                # we have a MDQ set from adjacent blocks
                prescriptionItms['MedProdName'] = orphanedMedProd[0]
                prescriptionItms['MedProdID'] = orphanedMedProd[1]
                prescriptionItms['Quantity'] = orphanedQuantity
                prescriptionItms['IDType'] = 'Adjacent block MDQ'
                prescriptionItmsLst.append(copy.deepcopy(prescriptionItms))
                medProdProcessedLineNos.append(copy.deepcopy(orphanedMedProd[2]))
                # reset the orphan variables
                orphanedMedProd = ()
                orphanedDirections = 0
                orphanedQuantity = u''
            else:
                # we don't have MDQ so reset the orphan variables
                orphanedMedProd = ()
                orphanedDirections = 0
                orphanedQuantity = u''

          

    write_http_response(200, prescriptionItmsLst)