import os
import cv2
import time
import requests
import numpy as np
import configparser
from bs4 import BeautifulSoup
from keras.models import load_model
from asyncio import run

class CourseBot:

    def __init__(self, account, password):
        self.account = account
        self.password = password
        self.coursesDB = {}

        # for keras
        self.model = load_model('model.h5')
        self.n_classes = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'

        # for requests
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36'

        self.loginUrl = 'https://isdna1.yzu.edu.tw/CnStdSel/Index.aspx'
        self.captchaUrl = 'https://isdna1.yzu.edu.tw/CnStdSel/SelRandomImage.aspx'
        self.courseListUrl = 'https://isdna1.yzu.edu.tw/CnStdSel/SelCurr/CosList.aspx'
        self.courseSelectUrl = 'https://isdna1.yzu.edu.tw/CnStdSel/SelCurr/CurrMainTrans.aspx?mSelType=SelCos&mUrl='

        self.loginPayLoad = {
            '__VIEWSTATE': '',
            '__VIEWSTATEGENERATOR': '',
            '__EVENTVALIDATION': '',
            'DPL_SelCosType': '',
            'Txt_User': self.account,
            'Txt_Password': self.password,
            'Txt_CheckCode': '',
            'btnOK': '確定'
        }

        self.selectPayLoad = {}

    async def predict(self, img):

        prediction = self.model.predict(np.array([img]))

        predicStr = ""
        for pred in prediction:
            predicStr += self.n_classes[np.argmax(pred[0])]

        return predicStr

    async def captchaOCR(self):

        captchaImg = cv2.imread('captcha.png') / 255.0
        return await self.predict(captchaImg)

    # login into system and get session
    async def login(self):
        
        while True:
            # clear Session object
            self.session.cookies.clear()

            # download and recognize captch
            with self.session.get(self.captchaUrl, stream= True) as captchaHtml:
                with open('captcha.png', 'wb') as img:
                    img.write(captchaHtml.content)
            captcha = await self.captchaOCR()

            # get login data
            loginHtml = self.session.get(self.loginUrl)
            
            # check if system is open
            if '選課系統尚未開放!' in loginHtml.text:
                await self.log('選課系統尚未開放!')
                continue

            # use BeautifulSoup to parse html
            parser = BeautifulSoup(loginHtml.text, 'lxml')

            # update login payload
            self.loginPayLoad['__VIEWSTATE'] = parser.select("#__VIEWSTATE")[0]['value']
            self.loginPayLoad['__VIEWSTATEGENERATOR'] = parser.select("#__VIEWSTATEGENERATOR")[0]['value']
            self.loginPayLoad['__EVENTVALIDATION'] = parser.select("#__EVENTVALIDATION")[0]['value']
            self.loginPayLoad['DPL_SelCosType'] = parser.select("#DPL_SelCosType option")[1]['value']
            self.loginPayLoad['Txt_CheckCode'] = captcha

            result = self.session.post(self.loginUrl, data= self.loginPayLoad)
            if ("parent.location ='SelCurr.aspx?Culture=zh-tw'" in result.text): #成功登入訊息可能一直改，挑個不太能改的
                await self.log('Login Successful! {}'.format(captcha))
                break
            elif ("資料庫發生異常" in result.text): # 僅比較成功登入及帳號密碼錯誤的訊息，不確定是否還有其他種情況也符合這個條件
                await self.log('帳號或密碼錯誤，請重新確認。')
            elif ("您未在此階段選課時程之內!請於時程內選課!!" in result.text):
                await self.log('您未在此階段選課時程之內!請於時程內選課!!')
            else:
                await self.log("Login Failed, Re-try!")
                continue
            exit(0)

    async def getCourseDB(self, depts):

        for dept in depts:
            # use BeautifulSoup to parse html
            html = self.session.get(self.courseListUrl)
            if "異常登入" in html.text:
                await self.log("異常登入，休息10分鐘!")
                time.sleep(600) # sleep 10 min
                continue
            parser = BeautifulSoup(html.text, 'lxml')

            self.selectPayLoad[dept] = {
                '__EVENTTARGET': 'DPL_Degree',
                '__EVENTARGUMENT': '',
                '__LASTFOCUS': '',
                '__VIEWSTATE': parser.select("#__VIEWSTATE")[0]['value'],
                '__VIEWSTATEGENERATOR': parser.select("#__VIEWSTATEGENERATOR")[0]['value'],
                '__VIEWSTATEENCRYPTED': '',
                '__EVENTVALIDATION': parser.select("#__EVENTVALIDATION")[0]['value'],
                'Hidden1': '',
                'Hid_SchTime': '',
                'DPL_DeptName': dept,
                'DPL_Degree': '6',
            }

            # use BeautifulSoup to parse html
            html = self.session.post(self.courseListUrl, data= self.selectPayLoad[dept])
            if "Error" in html.text:
                await self.log('Wrong coursesList, please check it again!')
                exit(0)
            parser = BeautifulSoup(html.text, 'lxml')

            # parse and save courses information
            courseList = parser.select("#CosListTable input")
            for courseInfo in courseList:
                tokens = courseInfo.attrs['name'].split(',') # SelCos,CS354,A,1,F,3,Y,Chinese,CS354,A,3 電腦與網路安全概論

                key = tokens[1] + tokens[2]
                courseName = '{} {}'.format(key, tokens[-1].split(' ')[1])

                self.coursesDB[key] = {
                    'name': courseName,
                    'mUrl': courseInfo.attrs['name']
                }
                # self.log(self.coursesDB[key])

            await self.log('Get {} Data Completed!'.format(dept))



    async def selectCourses(self, coursesList, delay = 0):
        while len(coursesList) > 0:
            for course in coursesList.copy():
                tokens = course.split(',')
                dept = tokens[0]
                key  = tokens[1]
                
                # check if the classID is legal
                if key not in self.coursesDB:
                    await self.log('{} is not a legal classID'.format(key))
                    coursesList.remove(course)
                    continue
                
                # simulte click button
                html = self.session.post(self.courseListUrl, data= self.selectPayLoad[dept])
                parser = BeautifulSoup(html.text, 'lxml')

                selectPayLoad = {
                    '__EVENTTARGET': '',
                    '__EVENTARGUMENT': '',
                    '__LASTFOCUS': '',
                    '__VIEWSTATE': parser.select("#__VIEWSTATE")[0]['value'],
                    '__VIEWSTATEGENERATOR': parser.select("#__VIEWSTATEGENERATOR")[0]['value'],
                    '__VIEWSTATEENCRYPTED': '',
                    '__EVENTVALIDATION': parser.select("#__EVENTVALIDATION")[0]['value'],
                    'Hidden1': '',
                    'Hid_SchTime': '',
                    'DPL_DeptName': dept,
                    'DPL_Degree': '6',
                    self.coursesDB[key]['mUrl'] + '.x': '0', 
                    self.coursesDB[key]['mUrl'] + '.y': '0'
                }
                self.session.post(self.courseListUrl, data= selectPayLoad)

                # select course
                html = self.session.get(self.courseSelectUrl + self.coursesDB[key]['mUrl'] + ' ,B,')

                # check if successful
                parser = BeautifulSoup(html.text, 'lxml')
                alertMsg = parser.select("script")[0].string.split(';')[0]
                await self.log('{} {}'.format(self.coursesDB[key]['name'], alertMsg[7:-2]))

                if "加選訊息：" in alertMsg or "已選過" in alertMsg:
                    coursesList.remove(course)
                elif "please log on again!" in alertMsg:
                    await self.login()

                time.sleep(delay)

    async def log(self, msg):

        print(time.strftime("[%Y-%m-%d %H:%M:%S]", time.localtime()), msg)


if __name__ == '__main__':
    configFilename = 'accounts.ini'
    if not os.path.isfile(configFilename):
        with open(configFilename, 'a') as f:
            f.writelines(["[Default]\n", "Account= your account\n", "Password= your password"])
            print('input your username and password in accounts.ini')
            exit()
    # get account info fomr ini config file
    config = configparser.ConfigParser()
    config.read(configFilename)
    Account = config['Default']['Account']
    Password = config['Default']['Password']

    # the courses you want to select, format: '`deptId`,`courseId``classId`'
    # 304 CSE
    
    coursesList = [
        '304,CS213B'
    ]

    # Time Parameter, sleep n seconds
    delay = 1
    
    depts = set([i.split(',')[0] for i in coursesList])
    
    myBot = CourseBot(Account, Password)
    run(myBot.login())
    run(myBot.getCourseDB(depts))
    run(myBot.selectCourses(coursesList, delay))
