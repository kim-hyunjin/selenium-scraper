from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
import requests
from PIL import Image # pillow
import json
import random
from requests_toolbelt.multipart.encoder import MultipartEncoder
import logging
import os

from opensea_tokens import OpenseaTokenScraper

class OpenseaCollectionScraper:
    def __init__(self, driver: webdriver, numOfCollections: int, maxNumOfAssets: int, authKey: str) -> None:
        self.__driver = driver
        self.__numOfCollections = numOfCollections
        self.__maxNumOfAssets = maxNumOfAssets
        self.__authKey = authKey
        self.tokenScraper = OpenseaTokenScraper(driver, authKey)

        # 컬렉션 관련
    def scrapeCollection(self) -> None:
        collectionUrls = self.__getCollectionUrls()
        for i in range(self.__numOfCollections):
            collectionInfo = self.__createCollection(collectionUrls[i])
            if collectionInfo == None:
                continue
            self.tokenScraper.scrapeTokens(collectionInfo)

    def __getCollectionUrls(self) -> list:
        self.__driver.get(self.__rancomCategory())
        self.__driver.implicitly_wait(5)
        self.__randomScrollDown()

        collectionUrls = []
        while True:
            collections = self.__driver.find_elements(By.CSS_SELECTOR, "a.CarouselCard--main")
            for collection in collections:
                collectionUrls.append(collection.get_attribute('href'))
            self.__driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
            if len(collectionUrls) > self.__numOfCollections: break

        return collectionUrls

    def __randomScrollDown(self) -> None:
        for _ in range(random.randrange(0, 10)):
            self.__driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
        self.__driver.implicitly_wait(5)

    def __rancomCategory(self) -> str:
        self.__driver.get('https://opensea.io/explore-collections')
        self.__driver.implicitly_wait(5)
        category = self.__driver.find_element(By.CSS_SELECTOR, "#main ul")
        tabLinks = category.find_elements(By.CSS_SELECTOR, "li > a")
        tabUrls = []
        for link in tabLinks:
            tabUrls.append(link.get_attribute('href'))
        return random.choice(tabUrls)

    def __createCollection(self, url):
        logging.info('collection url: {}'.format(url))
        self.__driver.get(url)
        self.__driver.implicitly_wait(5)
        
        img = self.__getCollectionImage()
        maxItemCnt = self.__getMaxItemNum()
        collectionInfo = self.__getCollectionInfo()
        res = self.__sendCollectionToServer(img, collectionInfo)
        if res.status_code != 200:
            logging.warning('컬렉션 생성 실패')
            return None

        resBody = res.json()
        collectionInfo["collection_id"] = resBody["collection"]["id"]
        collectionInfo["item_cnt"] = random.randrange(1, min([self.__maxNumOfAssets, maxItemCnt]))
        return collectionInfo

    def __sendCollectionToServer(self, img: Image, collection):
        url = os.getenv('COLLECTION_API_URL')
        imgIO = BytesIO()
        img.save(imgIO, img.format)
        img_format = img.format.lower()
        encoded = MultipartEncoder(
            fields={
                'thumbnailImage': ("thumbnail.{}".format(img_format), imgIO, 'image/{}'.format(img_format)),
                'json': json.dumps(collection)
            }
        )
        headers = {
            'accept': 'application/json',
            'Content-Type': encoded.content_type,
            'Authorization': "Bearer {}".format(self.__authKey)
        }
        res = requests.post(url, headers=headers, data=encoded)
        logging.info('collection {} {}'.format(collection["name"], res.status_code))
        return res

    def __getCollectionImage(self):
        collectionImg = self.__driver.find_element(By.CSS_SELECTOR, ".CollectionHeader--collection-image > img")
        imgUrl = collectionImg.get_attribute('src')
        imgRes = requests.get(imgUrl)
        img = Image.open(BytesIO(imgRes.content))
        return img

    def __getMaxItemNum(self):
        itemStatus = self.__driver.find_element(By.CLASS_NAME, 'CollectionStatsBar--bottom-bordered div[tabIndex="-1"]')
        try:
            return int(itemStatus.get_attribute('innerHTML'))
        except:
            return self.__maxNumOfAssets

    def __getCollectionInfo(self):
        collectionInfo = {}
        collectionName = self.__driver.find_element(By.TAG_NAME, "h1").text
        collectionInfo["name"] = collectionName
        collectionInfo["symbol"] = collectionName[:3].upper()
        try:
            desc = self.__driver.find_element(By.CSS_SELECTOR, "CollectionHeader--description > span")
            collectionInfo["description"] = desc.text
        except:
            collectionInfo["description"] = ""

        collectionInfo["type"] = random.choice(["erc721", "erc1155"])

        return collectionInfo