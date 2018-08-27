""" Module to parse the textblocks produced in an earlier function and identify
    the prescription items

    Python Version : 2.7
        Written using Python 2.7 because that's what azure functions supports
        natively - want to convert to python 3 as soon as practicable.
    To Do:
        get a count of the number of calls to LUIS and the
        cost of Cosmos DB calls
        make this run-able as a function - testable as a script

"""
from __future__ import print_function
from pydocumentdb import document_client
import sys
import json
import requests
import os
import ConfigParser
from pprint import pprint as pp

__author__ = 'David.Burnham@microsoft.com'

config = ConfigParser.ConfigParser()
config.read('config.ini')

LUIS_URL = config.get('FINDSCRIPTITEMS', 'LUIS_URL')
SUB_KEY = config.get('FINDSCRIPTITEMS', 'SUB_KEY')
LUIS_MATCH_SCORE_MIN = config.getfloat('FINDSCRIPTITEMS', 'LUIS_MATCH_SCORE_MIN')

CdbURI = config.get('FINDSCRIPTITEMS', 'CdbURI')
CdbKey = config.get('FINDSCRIPTITEMS', 'CdbKey')
CdbID = config.get('FINDSCRIPTITEMS', 'CdbID')
CdbCollID = config.get('FINDSCRIPTITEMS', 'CdbCollID')

_AZURE_FUNCTION_DEFAULT_METHOD = "POST"
_AZURE_FUNCTION_HTTP_INPUT_ENV_NAME = "req"
_AZURE_FUNCTION_HTTP_OUTPUT_ENV_NAME = "res"
_REQ_PREFIX = "REQ_"


def lookupMedProd(medProdStr):
    """check the medical products store in CosmosDB for the product
    Todo:
        This only does exact matches - need fuzzy matching
        There is almost no error handling - what if the network
            database is not available?
    """
    query = {'query': "SELECT * FROM prescriptionItems p WHERE p.MEDICINAL_PRODUCT_NAME = '{0}'".format(medProdStr)}
    docs = CdbClient.QueryDocuments(coll_link, query)
    resLst = list(docs)
    resDict = dict()
    if len(resLst) == 1:
        resDict['search'] = 'oneFound'
        resDict['medical_product_name'] = resLst[0][u'MEDICINAL_PRODUCT_NAME']
        resDict['product_id'] = resLst[0][u'id']
        return resDict
    else:
        # do something sensible if we get none or many results back
        resDict['search'] = 'notOneFound'
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
        if resDir['topScoringIntent']['score'] > LUIS_MATCH_SCORE_MIN:
            resDir['result'] = 'success'
            return resDir
        else:
            resDir['result'] = 'inconclusive'
            return resDir
    else:
        resDir = dict()
        resDir['result'] = 'callFailed'
        return resDir


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


textBlockjson = '''
[
  [
    {
      "lineNo": 0,
      "lineTxt": "Number of days' treatment"
    },
    {
      "lineNo": 2,
      "lineTxt": "N.B. Ensure dose is stated"
    },
    {
      "lineNo": 3,
      "lineTxt": "Endorsements"
    }
  ],
  [
    {
      "lineNo": 4,
      "lineTxt": "Cetirizine 10mg tablets"
    },
    {
      "lineNo": 5,
      "lineTxt": "1 EVERY DAY"
    },
    {
      "lineNo": 6,
      "lineTxt": "30 tablet"
    }
  ],
  [
    {
      "lineNo": 1,
      "lineTxt": "NHS Number:"
    }
  ],
  [
    {
      "lineNo": 7,
      "lineTxt": "1 item on this prescription"
    }
  ]
]
'''

if __name__ == '__main__':
    nofPrescriptionItemsLnCnt = 0

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

    # deserialize the json
    textBlocks = json.loads(textBlockjson)

    # process each line in the blocks with the LUIS model
    # iterate around the text blocks
    # update the textblocks object with the LUIS results
    # if we find a MedicinalProduct in LUIS - cross reference it in the CosmosDB catalog and get the product_id
    for tbidx, textBlock in enumerate(textBlocks):
        # iterate over lines in the text block
        for blockLineIdx, line in enumerate(textBlock):
            LUIScallRes = makeLUIScall(line['lineTxt'])
            if LUIScallRes['result'] == 'success':
                # Update the textblocks object with the LUIS results
                textBlocks[tbidx][blockLineIdx]['LUISintent'] = LUIScallRes['topScoringIntent']['intent']
                textBlocks[tbidx][blockLineIdx]['LUISscore'] = LUIScallRes['topScoringIntent']['score']
                if LUIScallRes['topScoringIntent']['intent'] == 'prescriptionItemNumber':
                    if len(LUIScallRes['entities']) == 1:
                        print(LUIScallRes['entities'][0]['entity'] + ' Item(s) on this prescription')
                        nofPrescriptionItemsLnCnt += 1
                        prescribedItems = int(LUIScallRes['entities'][0]['entity'])
                        textBlocks[tbidx][blockLineIdx]['NofPrecriptionItems'] = int(LUIScallRes['entities'][0]['entity'])
                elif LUIScallRes['topScoringIntent']['intent'] == 'medicinalProductName':
                    # See if we find a match for the medicinalProduct in cosmosDB
                    medProdDir = lookupMedProd(line['lineTxt'])
                    if medProdDir['search'] == 'oneFound':
                        textBlocks[tbidx][blockLineIdx]['catalogProductName'] = medProdDir['medical_product_name']
                        textBlocks[tbidx][blockLineIdx]['catalogProductID'] = medProdDir['product_id']

    # verify that we only have one or zero values for the number of prescription items
    if nofPrescriptionItemsLnCnt == 0:
        print("Warning - Did not find indication of count of items on prescription")
    elif nofPrescriptionItemsLnCnt > 1:
        print("Error - Found more than one indication of count of items on prescription")
        exit(-1)

    prescribedItemsLst = []
    # Check for blocks where we have medicinalProductName, directions and quantity
    for tbidx, textBlock in enumerate(textBlocks):
        # check each block to see if it has a medicinalProductName, directions and quantity
        medProdFlg = False
        dirFlg = False
        quantFlg = False
        medProduct = ''
        medProdQuant = ''
        medProdID = ''
        for blockLineIdx, line in enumerate(textBlock):
            if line['LUISintent'] == "medicinalProductName" and line['LUISscore'] > LUIS_MATCH_SCORE_MIN:
                medProdFlg = True
                medProduct = line['lineTxt']  # may want to change this to line['catalogProductName']
                medProdID = line['catalogProductID']
            elif line['LUISintent'] == "directions" and line['LUISscore'] > LUIS_MATCH_SCORE_MIN:
                dirFlg = True
            elif line['LUISintent'] == "quantity" and line['LUISscore'] > LUIS_MATCH_SCORE_MIN:
                quantFlg = True
                medProdQuant = line['lineTxt']
        if medProdFlg and dirFlg and quantFlg:
            # we have a block with medicinalProductName, directions and quantity
            prescribedItemsLst.append({'medicinalProductName': medProduct, 'medicalProductID': medProdID,
                                       'quantity': medProdQuant})

    print('Prescription items found')

    for prescribedItem in prescribedItemsLst:
        print(prescribedItem)

    pp(textBlocks)

    print('Script Ends!')
