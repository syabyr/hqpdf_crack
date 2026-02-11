import logging

#create a logger
logger = logging.getLogger('mylogger')
#set logger level
logger.setLevel(logging.INFO)
#or you can set the following level
#logger.setLevel(logging.DEBUG)

handler = logging.FileHandler('mylog.log')
# create a logging format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

#write a info message
logger.info('This is an INFO message')