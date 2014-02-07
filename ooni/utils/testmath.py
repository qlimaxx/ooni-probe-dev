from BeautifulSoup import BeautifulSoup
from math import *
from ooni.utils import log

#Set of tags found in modern websites and not likely to be found in the same
#proportion as a block page.
tags = ['html','head','title','body','script','meta','link','div','ul','li','span','a','iframe','img','p','form','input']          


#TO-DO BEFORE COMMIT: Revise this
#Given two HTML documents, calculate their cosine similarity based
#on vectors of their respective tag counts
def cosine_similarity(experiment, control,url):
    try:
        (exp_vector, ex_valid) = construct_vector(experiment)
        (control_vector, control_valid) = construct_vector(control)        
        if ex_valid and control_valid:
            return str(dot_product(exp_vector, control_vector) / (magnitude(exp_vector)*magnitude(control_vector)))
        else:
            return 'Cosine similarity test failed\nexp_vector: ' + str(exp_vector) + '\ncontrol_vector: ' + str(control_vector) + '\n' + url
    except Exception, e:
        log.err(e)
        log.err('exp_vector: ' + str(exp_vector))
        log.err('control_vector: ' + str(control_vector))
        log.err('exp_vector: ' + str(dot_product(exp_vector,control_vector)))
        log.err('URL: ' + str(url))        

#Given two vectors, compute their dot product
def dot_product(vector1, vector2):
    dp = 0
    for i in range(len(vector1)):
        dp += vector1[i]*vector2[i]
    return dp

#Args: htmldoc is a string containing the page HTML
def construct_vector(htmldoc):
    text = BeautifulSoup(htmldoc)
    page_vector = []
    global tags
    parsed_ok = False
    
    for tag in tags:
        #Find all instances of the tag we're concerned with
        #and get the length of the array the search returns.
        t = len(text.findAll(tag))
        page_vector.append(t)
        if t > 0:
            parsed_ok = True
    return (page_vector, parsed_ok)
        
#Given a vector, compute its magnitude
def magnitude(v):
    m = 0
    for num in v:
        m = m + (num * num)
    return sqrt(m)
