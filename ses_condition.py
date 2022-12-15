import codecs
import configparser
import glob
import io
import os
import pathlib
import sys
import threading
import urllib.request
from datetime import datetime
from time import sleep

import cv2
import img2pdf
import numpy as np
import pandas as pd
import pymysql
from PIL import Image
from PyPDF2 import PdfFileMerger, PdfFileReader
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from telegram.ext import Updater

# Задаем переменные путей (если папка есть, то чистим, если нет, то создаем)
# Проверяем запущен .py файл или .exe и в зависимости от этого получаем пути

if getattr(sys, 'frozen', False):
    windy_path = f'{pathlib.Path(sys.executable).parent.absolute()}/windy/'
    if not os.path.exists(windy_path): os.makedirs(windy_path)
    list(map(os.unlink, (os.path.join(windy_path, f) for f in os.listdir(windy_path))))
    cam_path = f'{pathlib.Path(sys.executable).parent.absolute()}/cam/'
    if not os.path.exists(cam_path): os.makedirs(cam_path)
    list(map(os.unlink, (os.path.join(cam_path, f) for f in os.listdir(cam_path))))
    result_path = f'{pathlib.Path(sys.executable).parent.absolute()}/result/'
    if not os.path.exists(result_path): os.makedirs(result_path)
    list(map(os.unlink, (os.path.join(result_path, f) for f in os.listdir(result_path))))
    parent_path = str(pathlib.Path(sys.executable).parent.absolute())
    nosignal_image = f'{pathlib.Path(sys.executable).parent.absolute()}/nosignal.jpg'
    gecko_path = f'{pathlib.Path(sys.executable).parent.absolute()}/geckodriver.exe'
    firefox_path = f'{pathlib.Path(sys.executable).parent.absolute()}/FirefoxPortable/App/Firefox64/firefox.exe'
    settings = f'{pathlib.Path(sys.executable).parent.absolute()}/settings.ini'
elif __file__:
    windy_path = f'{pathlib.Path(__file__).parent.absolute()}/windy/'
    if not os.path.exists(windy_path): os.makedirs(windy_path)
    list(map(os.unlink, (os.path.join(windy_path, f) for f in os.listdir(windy_path))))
    cam_path = f'{pathlib.Path(__file__).parent.absolute()}/cam/'
    if not os.path.exists(cam_path): os.makedirs(cam_path)
    list(map(os.unlink, (os.path.join(cam_path, f) for f in os.listdir(cam_path))))
    result_path = f'{pathlib.Path(__file__).parent.absolute()}/result/'
    if not os.path.exists(result_path): os.makedirs(result_path)
    list(map(os.unlink, (os.path.join(result_path, f) for f in os.listdir(result_path))))
    parent_path = str(pathlib.Path(__file__).parent.absolute())
    nosignal_image = f'{pathlib.Path(__file__).parent.absolute()}/nosignal.jpg'
    gecko_path = f'{pathlib.Path(__file__).parent.absolute()}/geckodriver.exe'
    firefox_path = f'{pathlib.Path(__file__).parent.absolute()}/FirefoxPortable/App/Firefox64/firefox.exe'
    settings = f'{pathlib.Path(__file__).parent.absolute()}/settings.ini'

# Получаем настройки из ini файла конфигурации

config = configparser.ConfigParser()
config.read(settings)
bot_token = config["settings"].get("bot_token")
channel_id = config["settings"].get("channel_id")
time_cutoff = float(config["settings"].get("time_cutoff"))
host_ini = config["settings"].get("host_ini")
user_ini = config["settings"].get("user_ini")
port_ini = int(config["settings"].get("port_ini"))
password_ini = config["settings"].get("password_ini")
database_ini = config["settings"].get("database_ini")

# Настройки для драйвера Firefox
# (скрытый режим и установка драйвера(закомменчена),
# теперь берется geckodriver.exe из этой же папки и
# portable версия firefox (чтобы работало даже на чистой системе))

options = Options()
options.headless = True
options.binary_location = firefox_path
serv = Service(gecko_path)

# browser = webdriver.Firefox(options=options, executable_path=GeckoDriverManager().install())
browser = webdriver.Firefox(options=options, service=serv)

# Получаем список ссылок из БД

connection = pymysql.connect(
        host=host_ini,
        user=user_ini,
        port=port_ini,
        password=password_ini,
        database=database_ini)
with connection.cursor() as cursor:

    # Условие если текущее время меньше 9 часов,
    # то работаем по второй ценовой зоне, если больше, то по первой.

    if time_cutoff > datetime.now().hour:
        sql = "select ses,ses_eng,cam,windy from cams where price_zone='2';"
    else:
        sql = "select ses,ses_eng,cam,windy from cams where price_zone='1';"
    cursor.execute(sql)
    ses_url = pd.DataFrame(
        cursor.fetchall(),
        columns=['ses', 'ses_eng', 'cam', 'windy']
    )
    connection.close()
    ses_url['dt'] = 0
    ses_url.head()
for windy_url in range(len(ses_url)):
    windy = str(ses_url.windy[windy_url])
    ses_name = str(ses_url.ses[windy_url])
    ses_name_eng = str(ses_url.ses_eng[windy_url])
    cam_url = str(ses_url.cam[windy_url])

    # Получаем скрин погоды windy

    browser.get(windy)
    browser.set_window_size(5120, 1440)
    sleep(5)
    WebDriverWait(browser, 10).until(EC.presence_of_element_located(
        (By.CLASS_NAME, 'fg-red.size-xs.inlined.clickable')
        )
    )
    click_button = browser.find_element_by_class_name(
        'fg-red.size-xs.inlined.clickable'
    )
    browser.execute_script("arguments[0].click();", click_button)
    sleep(1)

    # Найдем высоту таблицы с погодой (если она меньше 269.5,
    # то пробуем обновить страницу)(на случай непрогруза страницы)

    HeightElement = browser.find_element_by_id(
        'detail-data-table'
    ).size['height']
    if HeightElement < 200:
        browser.refresh()
        WebDriverWait(browser, 10).until(EC.presence_of_element_located(
            (By.CLASS_NAME, 'fg-red.size-xs.inlined.clickable')
            )
        )
        click_button = browser.find_element_by_class_name(
            'fg-red.size-xs.inlined.clickable'
        )
        browser.execute_script("arguments[0].click();", click_button)
        sleep(1)
    featureelement = browser.find_element_by_id(
        'detail-data-table'
    ).screenshot_as_png

    # Найдем ширину таблицы с погодой(меняется от времени просмотра прогноза)

    WidthElement = browser.find_element_by_id(
        'detail-data-table'
    ).size['width']
    imagestream = io.BytesIO(featureelement)
    im = Image.open(imagestream)
    im.save(f'{windy_path}{ses_name_eng}.png')

    # Получаем скрин с камеры
    # Проверка доступен ли вообще url

    try:
        code_url = urllib.request.urlopen(cam_url).getcode()
        print(ses_name)
        print(code_url)
        if code_url == 200:

            # Если доступ есть, то пробуем захватить кадр

            def cap_try(cam_url):
                cv2.VideoCapture(cam_url)
            e = threading.Event()
            t = threading.Thread(target=cap_try, args=(cam_url,))
            t.start()
            t.join(7.0)
            if t.is_alive():
                frame = cv2.imread(nosignal_image)
                t.join(7.0)
                e.set()
            else:
                cap = cv2.VideoCapture(cam_url)
                t.join()
                print(cap)

                # Если ссылка открылась, то брать картинку

                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()

                    # Если камера не работает (нет потока видео),
                    #  то брать картинку "нет сигнала"

                    if ret is False:
                        frame = cv2.imread(nosignal_image)
                else:
                    if cap is None:
                        frame = cv2.imread(nosignal_image)
        else:
            frame = cv2.imread(nosignal_image)
    except Exception:
        frame = cv2.imread(nosignal_image)

    # Находим размеры изображения с камеры и масштабируем под размер картинки с погодой
    WidthFrame = int(frame.shape[1])
    s = WidthFrame/WidthElement
    HeightCam = int(frame.shape[0]/s)
    WidthCam = int(WidthElement)
    dsize = (WidthCam, HeightCam)
    frame = cv2.resize(frame, dsize)
    writestatus = cv2.imwrite(
        f'{cam_path}{ses_name_eng}.png',
        frame,
        [int(cv2.IMWRITE_PNG_COMPRESSION), 9]
    )

    # Склеиваем 2 скрина

    img1 = cv2.imread(f'{cam_path}{ses_name_eng}.png')
    img2 = cv2.imread(f'{windy_path}{ses_name_eng}.png')
    vis = np.concatenate((img1, img2), axis=0)

    # Добавляем на скрин с камеры название СЭС

    cv2.rectangle(vis, (0, 0), (900, 80), (255, 255, 255), -1)
    cv2.putText(
        vis,
        ses_name,
        (10, 50),
        cv2.FONT_HERSHEY_COMPLEX,
        2,
        (0, 0, 0),
        2
    )

    # Сохраняем итоговую картинку со сжатием

    cv2.imwrite(
        f'{result_path}{ses_name_eng}.png',
        vis,
        [int(cv2.IMWRITE_PNG_COMPRESSION), 9]
    )

    # Конвертируем итоговую png в pdf
    # (нужно для создания итогового pdf с закладками)

    with open(f'{result_path}{ses_name}.pdf', "wb") as f:
        f.write(img2pdf.convert(glob.glob(f'{result_path}{ses_name_eng}.png')))
browser.quit()
browser.__exit__()
cv2.destroyAllWindows()

# Создаем PDF

path = result_path
time_for_name = datetime.now().strftime('%d.%m.%Y')
if time_cutoff > datetime.now().hour:
    output_filename = f'ses_condition_sib_{time_for_name}.pdf'
else:
    output_filename = f'ses_condition_eur_{time_for_name}.pdf'

# Функция получения списка pdfок из папки result


def getfilenames(filepath=path, filelist_out=[], file_ext='all'):
    for fpath, dirs, fs in os.walk(filepath):
        for f in fs:
            fi_d = os.path.join(fpath, f)
            if file_ext == 'all':
                filelist_out.append(fi_d)
            elif os.path.splitext(fi_d)[1] == file_ext:
                filelist_out.append(fi_d)
            else:
                pass
    return filelist_out

# Функция слияния итоговой pdf с закладками из нескольких pdf


def mergefiles(path, output_filename, import_bookmarks=False):
    merger = PdfFileMerger()
    filelist = getfilenames(filepath=path, file_ext='.pdf')
    if len(filelist) == 0:
        print('There is no pdf file in the current directory')
        sys.exit()
    for filename in filelist:
        f = codecs.open(filename, 'rb')
        file_rd = PdfFileReader(f)
        short_filename = os.path.basename(os.path.splitext(filename)[0])
        if file_rd.isEncrypted:
            print('Unsupported encrypted file: %s' % (filename))
            continue
        merger.append(
            file_rd,
            bookmark=short_filename,
            import_bookmarks=import_bookmarks
        )
        print('Merged files: %s' % (filename))
        f.close()
    out_filename = os.path.join(os.path.abspath(path), output_filename)
    merger.write(out_filename)
    print('Combined output file: %s' % (out_filename))
    merger.close()

# Запуск функций получения итоговой pdf


mergefiles(path, output_filename)

# Отправляем PDF в Telegram

updater = Updater(bot_token)
updater.bot.send_document(
    chat_id=channel_id,
    document=open(f'{result_path}{output_filename}', 'rb'),
    timeout=100.0
)
print('Send PDF to Telegram done')
sleep(1) 
os._exit(1)
