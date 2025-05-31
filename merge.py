import os

from asyncio import run, gather
from modules import CourseBot, Json

async def main(config):
    bots = []
    for user in config:
        account = config[user]["Account"]
        password = config[user]["Password"]
        courseList = config[user]["courseList"]
        depts= set([i.split(',')[0] for i in courseList])
        print(f"Creating bot for {account}")
        bot= CourseBot(account, password)
        bots.append(bot.startup(coursesList=courseList, depts=depts))
    await gather(*bots)
    
    
if __name__ == '__main__':

    configFilename = './user.json'
    if not os.path.isfile(configFilename):
        with open(configFilename, 'a') as f:
            f.writelines(["[Default]\n", "Account= your account\n", "Password= your password"])
            print('input your username and password in accounts.ini')
            exit()
    
    config= Json.load(configFilename)

    run(main(config))