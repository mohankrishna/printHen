from __future__ import absolute_import
#from djcelery import celery
from celery.task import periodic_task
from celery.task.schedules import crontab
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from django.conf import settings
import datetime
import json
import easyimap
import cups
import itertools
import smtplib
import re
import traceback
from . import printhen_wit
from . import email_strip
from . import utils
from pprint import pprint
from subprocess import call
from email.mime.text import MIMEText
from .models import *
import datetime
import glob
import os

current_time_offline = datetime.datetime.now()
elapsed_time_offline = 0
prev_time_offline = datetime.datetime.now()

current_time_media_jam = datetime.datetime.now()
elapsed_time_media_jam = 0
prev_time_media_jam = datetime.datetime.now()
from_addr = ""

@shared_task
@periodic_task(run_every=datetime.timedelta(seconds=10))
def checkForMail():
    global from_addr;
    try:
        with open('/home/pi/printhen/credentials.json') as data_file:
            data = json.load(data_file)
            #pprint(data)
    except Exception,err:
        print err
        return
    host = data["imap_hostname"]
    user = data["username"]
    password = data["password"]
    admin_email = data["admin_email"]
    mailbox = "inbox"
    from_addr = ""
    try:     
        imapper = easyimap.connect(host, user, password, mailbox)
        op = {}
        options = {}
        mail1 = imapper.unseen(1)
        #print "HELLO"
        print mail1
        for mail in mail1:
            title = mail.title.encode("utf-8")
            body = mail.body.encode("utf-8")
            from_addr = mail.from_addr.encode("utf-8")

            # print "Checking for title =>" + title
            # title = title.upper()
            # if "PRINTHEN" in title:
            #     print "MAGIC TITLE PASSED"
            #     #printhen_response(data["username"], from_addr, "MAGIC TITILE PASSED")
            # else:
            #     print "MAGIC TITLE FAILED"
            #     printhen_response(data["username"], from_addr, "[no-reply]PRINTHEN-INVALID SUBJECT", "Hey buddy kindly send mail with PRINTHEN as subject in order to initiate the print")
            #     return


            from_addr = from_addr[from_addr.find("<")+1:from_addr.find(">")]
            print "====================="
            print "NEW MAIL "
            print "====================="
            print "from    : " + from_addr
            print "Message : " + body
            # if "begin print" not in body or "end print" not in body or "from" not in body or "to" not in body or "copies" not in body:
            #     printhen_response(data["username"], from_addr, "[no-reply] PRINTHEN. SYNTAX ERROR", "Syntax error. The correct syntax is: begin print from x to y copies z end print")
            #     return

            # else:
            #body = body[body.find("begin print")+11:body.find("end print")]
        
            if not mail.attachments:
                printhen_response(data["username"], from_addr, "PrintHen - No attachment found.", "Hello, guess you did not attached any files to print.")
                return
            op = parseBody(body)
            if('copies' not in op):
                printhen_response(data["username"],from_addr,"PrintHen - Email processing exception.","Hello printHen did not understand your email, can you write it a little differently!")
            conn = cups.Connection()
            print body
            print op
            if(('from_page' in op) and ('to_page' in op)):
                options['from'] = op['from_page']
                options['to']   = op['to_page']

            elif('page' in op):
                options['from'] = op['page']
                options['to']   = op['page']
            else:
                options['from'] = -1
                options['to']   = -1

            
                    
            if int(options['from']) > int(options['to']):
                printhen_response(data["username"], from_addr, "PrintHen - Error with print requirment.", "Your start-page value seems to be greater then the end page value.")
                return
            for attachment in mail.attachments:
                filename = settings.MEDIA_PATH + attachment[0]
                with open(filename, 'wb') as f:
                    f.write(attachment[1])
                #conn = cups.Connection()
                if(".pdf" not in attachment[0]):
                    name = attachment[0]
                    name = re.sub(r'\.(.*)','',name)
                    name = settings.MEDIA_PATH + name + ".pdf"  
                    print "converting " +  filename + " to " + name
                    print "calling " + "unoconv -f pdf -o " + name + " " + filename
                    call(["unoconv","-f","pdf","-o",name,filename])
                    filename = name
                finalOptions = {}
                finalOptions['copies'] = op['copies']
                if(op['onesided'] == True):
                    finalOptions['sides'] = 'one-sided'
                s = []
                if((options['from']== '-1') or (options['to']=='-1')):
                    pass
                    #do nothing
                # elif((op['from']== '-2') or (op['to']=='-2')):
                #     printhen_response(data["username"], from_addr, "[no-reply] PRINTHEN-COMMAND NOT UNDERSTOOD", "I didnt understand what you said can u  rephrase your sentence?")
                #     return
                else:
                    s.append(options['from'])
                    s.append("-")
                    s.append(options['to'])
                    s1 = ''.join(s)
                    finalOptions['page-ranges'] = s1
                print finalOptions
                printers = conn.getPrinters()
                for printer in printers:
                    print printers.items()
                    print printer, printers[printer]["device-uri"]
                    try:
                        pass
                        printer_returns = conn.printFile("printhen", filename, "print", finalOptions)
                    except cups.IPPError as (status, description):
                        print 'IPP status is %d' % status
                        print 'Meaning:', description
                        printhen_response(data["username"], from_addr, "PrintHen - Printer seems to be down.","Hello, there seems to be a problem with the printer, please check the printer and try again")
                        printhen_response(data["username"], admin_email, "Printhen - Exception while printing - error "+str(status) + " while printing for " +str(from_addr), description)
                        return
                    job_state = conn.getJobAttributes(printer_returns)["job-state"]
                    #job_state = 9
                    printer_state = {};
                    while(job_state!=9):
                        #print job_state
                        job_state = conn.getJobAttributes(printer_returns)["job-state"]
                        if(job_state == 5):
                            printer_state = conn.getPrinterAttributes("printhen",requested_attributes=["printer-state-reasons",])
                            #print printer_state
                        if(job_state == 8):
                            printhen_response(data["username"], from_addr, "PrintHen - Print job is aborted." ,"Hello, there seems to be a problem with the printer, please check the printer and try again   ")
                            return
                        if(job_state == 7):
                            printhen_response(data["username"], from_addr, "Printhen - Print job cancelled by admin" ,"Hello, your print job has been cancelled by the admin. kindly contact admin at " + str(admin_email))
                            return
                        for state in printer_state['printer-state-reasons']:
                            if("offline-report" in state):
                                printhen_response(data["username"], from_addr, "PrintHen-Printer seems to be down ." ,"Hello, there seems to be a problem with the printer, please check the printer and try again")
                                printhen_response(data["username"], admin_email, "PrintHen Admin - Printer is offline." ,"The Printer went offline, kindly check its condition and reboot printHen if necessary.")
                                
                                conn.cancelJob(printer_returns, purge_job=True)
                                return
                    updatePrintHistory(from_addr)
                    print "SUCCESS"

            printhen_response(data["username"], from_addr, "Printhen - Your print job is complete.","Your print has been successfully done.")
                        
        #printhen_response(data["username"], from_addr, "[no-reply] PRINTHEN",str(op))
        return "Success"
    except Exception,err:
        printhen_response(data["username"],from_addr,"PrintHen - Unknown exception report.","An unknown exception occurred kindly contact your  admin at " + admin_email); 
        printhen_response(data["username"],admin_email,"PrintHen - send trace to our developers.","kindly send the file /var/log/supervisorctl/celeryd_err.log to developer raghuram8892@gmail.com" )    
def updatePrintHistory(from_addr):
    print "updating Print History"
    try:
        print "MAIL SENT FROM"
        print from_addr
        history = PrintHistory.objects.get(from_addr=from_addr)
        print history
    except:
        history = None
        print "except"
        #traceback.print_exc()
    if history is not None:
        if(history.from_addr==from_addr):
            history.count = history.count + 1
            history.save()
    else:
        history = PrintHistory(from_addr=from_addr,count=1)
        history.save()
    
def printhen_response(from_addr, to_addr, subject, msg):
    msg1 = MIMEMultipart('alternative')
    msg1['Subject'] = subject
    msg1['From'] = from_addr
    msg1['To'] = to_addr
    html = utils.bake_email_template(to_addr,msg)
    part = MIMEText(html, 'html')
    msg1.attach(part)
    try:
        with open('credentials.json') as data_file:
            data = json.load(data_file)
        pprint(data)
    except:
        print "CREDENTIALS NOT FOUND"
        return
    s = smtplib.SMTP_SSL(data["smtp_hostname"], 465)
    #s.starttls()
    s.login(data["username"], data["password"])
    s.sendmail(from_addr, [to_addr], msg1.as_string())
    s.quit()

def parseBody(body):
    body = email_strip.strip_mail(body)
    d = printhen_wit.extract_information(body)
    return d

# @periodic_task(run_every=datetime.timedelta(minutes=55))
# def hello():
#       i = 0
#       print "hello"
#       hello()

# @celery.task
# def add():
#       return 2+3

@shared_task
@periodic_task(run_every=crontab(hour=21,minute=30))
#@periodic_task(run_every=datetime.timedelta(seconds=5))
def clean_up():
	print "CLEANING UP MEDIA"	
	p1 = "/home/pi/media/*"
	
	for fl in glob.glob(p1):
		os.remove(fl)    
	return 1

@shared_task
@periodic_task(run_every=crontab(hour=21,minute=50,day_of_week="fri"))
#@periodic_task(run_every=datetime.timedelta(seconds=60))
def reboot():
        print "REBOOTING PI FOR MAINTENANCE"
	cmd = "sudo reboot"
	call(cmd,shell=True)
	return 1


@shared_task
@periodic_task(run_every=datetime.timedelta(seconds=10))
def printer_maintenance():
    global elapsed_time_offline
    global elapsed_time_media_jam
    global prev_time_offline
    global prev_time_media_jam
    global current_time_offline
    global current_time_media_jam
    conn = cups.Connection();
    printer_state = conn.getPrinterAttributes("printhen",requested_attributes=["printer-state-reasons",])
    for state in printer_state['printer-state-reasons']:
                            if("offline-report" in state):
                                print "PRINTER OFFLINE"
                                current_time_offline = datetime.datetime.now()
                                elapsed_time_offline += current_time_offline.minute - prev_time_offline.minute
                                prev_time_offline = current_time_offline
				print "Printer offline for " + str(elapsed_time_offline) + "  minutes"
                                if(elapsed_time_offline > 2):
                                    printhen_response("raghuram8892@gmail.com", from_addr, "[no-reply] PRINTHEN-PRINTER OFFLINE" ,"Printer is offline kindly check it")
                                    elapsed_time_offline=0
                                    
                            if("offline-report" not in state):
                                elapsed_time_offline = 0
                                prev_time_offline = datetime.datetime.now()
                                current_time_offline = datetime.datetime.now()

                            if("media-jam-warning" in state):
                                print "MEDIA JAM DETECTED"
                                current_time_media_jam = datetime.datetime.now()
                                elapsed_time_media_jam  += current_time_media_jam.minute - prev_time_media_jam.minute
                                prev_time_media_jam = current_time_media_jam
                                print "ELAPSED TIME SINCE MEDIA JAM DETECTION"
                                print elapsed_time_media_jam
                                if(elapsed_time_media_jam > 10):
                                    #printhen_response("printhen77@gmail.com", "raghuram8892@gmail.com", "[no-reply] PRINTHEN-Media Jam" ,"MEDIA JAMMED")
                                    elapsed_time_media_jam = 0
   

#@shared_task
#@periodic_task(run_every=datetime.timedelta(seconds=10))
def clean_up_table(self):
    print "Cleaning up Database"
    try:
        PrintHistory.objects.all().delete()
    except:
        print "Exception Happened while deleting table" 
