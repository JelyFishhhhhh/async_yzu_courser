import asyncio
from tensorflow.keras.models import load_model  # type: ignore
import requests
import numpy as np
from bs4 import BeautifulSoup
import cv2
import time

class CourseBot:
    def __init__(self, account, password):
        self.account = account
        self.password = password
        self.coursesDB = {}

        # Keras OCR Model
        self.model = load_model('model.h5', compile=False)
        self.n_classes = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'

        # Requests session
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
        captchaImg = cv2.imread(f'{self.account}.png') / 255.0
        return await self.predict(captchaImg)

    async def login(self):
        while True:
            self.session.cookies.clear()

            # Download CAPTCHA
            with self.session.get(self.captchaUrl, stream= True) as captchaHtml:
                with open(f'{self.account}.png', 'wb') as img:
                    img.write(captchaHtml.content)
            captcha = await self.captchaOCR()

            # Get login page
            loginHtml = self.session.get(self.loginUrl)
            if '選課系統尚未開放!' in loginHtml.text:
                await self.log("選課系統尚未開放!")
                await asyncio.sleep(30)
                continue

            parser = BeautifulSoup(loginHtml.text, 'lxml')
            try:
                self.loginPayLoad.update({
                    '__VIEWSTATE': parser.select_one("#__VIEWSTATE")['value'],
                    '__VIEWSTATEGENERATOR': parser.select_one("#__VIEWSTATEGENERATOR")['value'],
                    '__EVENTVALIDATION': parser.select_one("#__EVENTVALIDATION")['value'],
                    'DPL_SelCosType': parser.select("#DPL_SelCosType option")[1]['value'],
                    'Txt_CheckCode': captcha,
                })
            except Exception:
                await self.log("HTML parsing error in login payload.")
                continue

            result = self.session.post(self.loginUrl, data=self.loginPayLoad)

            if "parent.location ='SelCurr.aspx?Culture=zh-tw'" in result.text:
                await self.log(f"Login Successful! Captcha: {captcha}")
                break
            elif "資料庫發生異常" in result.text:
                await self.log("帳號或密碼錯誤，請重新確認。")
                exit(1)
            elif "未在此階段選課" in result.text:
                await self.log("您未在此階段選課時程之內!")
                exit(1)
            else:
                await self.log("Login failed. Retrying...")
                await asyncio.sleep(2)

    async def getCourseDB(self, depts):
        for dept in depts:
            html = self.session.get(self.courseListUrl)
            if "異常登入" in html.text:
                await self.log("異常登入，休息10分鐘!")
                await asyncio.sleep(600)
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

            html = self.session.post(self.courseListUrl, data=self.selectPayLoad[dept])
            if "Error" in html.text:
                await self.log(f"[{dept}] Wrong coursesList.")
                exit(1)

            parser = BeautifulSoup(html.text, 'lxml')
            for course in parser.select("#CosListTable input"):
                tokens = course.attrs['name'].split(',')
                key = tokens[1] + tokens[2]
                name = f"{key} {tokens[-1].split(' ')[1]}"
                self.coursesDB[key] = {
                    'name': name,
                    'mUrl': course.attrs['name']
                }

            await self.log(f"Get {dept} Data Completed!")

    async def selectCourses(self, coursesList, delay=1):
        while len(coursesList) > 0:
            for course in coursesList.copy():
                tokens = course.split(',')
                dept = tokens[0]
                key  = tokens[1]
                # dept, key = course.split(',')
                if key not in self.coursesDB:
                    await self.log(f"{key} is not a legal classID")
                    coursesList.remove(course)
                    continue

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

                html = self.session.get(self.courseSelectUrl + self.coursesDB[key]['mUrl'] + ' ,B,')

                parser = BeautifulSoup(html.text, 'lxml')
                alertMsg = parser.select("script")[0].string.split(';')[0]
                await self.log(f"{self.coursesDB[key]['name']} {alertMsg[7:-2]}")

                if "加選訊息：" in alertMsg or "已選過" in alertMsg:
                    coursesList.remove(course)
                elif "please log on again!" in alertMsg:
                    await self.login()

                await asyncio.sleep(delay)

    async def log(self, msg):
        print(time.strftime("[%Y-%m-%d %H:%M:%S]"), f"[{self.account}] {msg}")

    async def startup(self, coursesList, depts, delay=1):
        await self.login()
        await self.getCourseDB(depts)
        await self.selectCourses(coursesList, delay)
