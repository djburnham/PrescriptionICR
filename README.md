# PrescriptionICR
Azure functions to allow the identification of prescription items from prescription scripts

textBlockScan - scans through the output of the Azure Cognitive Vision OCR service and puts text lines that are 
closely located into blocks

findScriptItems	 - goes through the output of textBlock scan and tries to identify prescription items
by classifying them with LUIS and looking for the precription item, directions and quantity in a block
run.py in the findScriptItems directory is the azure function script code.


