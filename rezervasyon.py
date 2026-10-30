from datetime import datetime, timedelta
import getpass
import os
import sys
import time

import cv2
import pytesseract
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://ktprezervasyon.uskudar.bel.tr/?p=2"
HEDEF_SEANS = "11:00"
ON_HAZIRLIK_SEANS = "19:00"
KOLTUK = "69-9"
YEDEK_INDEX = 2

# GitHub Secrets üzerinden veya doğrudan buradaki değişkenlerden okunur
TC_KIMLIK = os.environ.get("TC_KIMLIK", "17348539445")
SIFRE = os.environ.get("SIFRE", "Tahareda11!")
HEADLESS = True  # GitHub sunucularında arayüz olmadığı için True olmalı
HEMEN_BASLA = True

LOGIN_DENEME = 30
HAZIRLIK_SON = (23, 55)
REZ_DENEME = 3

# Hem Windows hem Linux (GitHub Actions) için Tesseract yolları
for yol in [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
]:
  if os.path.exists(yol):
    pytesseract.pytesseract.tesseract_cmd = yol
    break

print("Basliyor...")


def simdi():
  return datetime.now()


def hazirlik_son_zaman():
  n = simdi()
  if n.hour >= 12:
    return n.replace(
        hour=HAZIRLIK_SON[0], minute=HAZIRLIK_SON[1], second=0, microsecond=0
    )
  return n + timedelta(minutes=5)


def tc_sifre_al():
  tc = TC_KIMLIK or os.environ.get("TC_KIMLIK") or input("TC Kimlik No: ").strip()
  sifre = (
      SIFRE
      or os.environ.get("SIFRE")
      or getpass.getpass("Sifre (gizli): ")
  )
  if not tc or not sifre:
    raise RuntimeError("TC veya sifre bos.")
  return tc, sifre


def captcha_oku(img, deneme=10):
  for _ in range(deneme):
    try:
      img.screenshot("c.png")
      icv = cv2.imread("c.png")
      if icv is None:
        time.sleep(0.5)
        continue
      gray = cv2.cvtColor(icv, cv2.COLOR_BGR2GRAY)
      res = cv2.resize(gray, (0, 0), fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
      _, th = cv2.threshold(res, 140, 255, cv2.THRESH_BINARY)
      cv2.imwrite("ct.png", th)
      code = pytesseract.image_to_string(
          Image.open("ct.png"), config="--psm 8 -c tessedit_char_whitelist=0123456789"
      ).strip()
      if len(code) == 6 and code.isdigit():
        return code
    except Exception:
      pass
    time.sleep(0.1)
  return None


def giris_yap(driver, tc, sifre):
  son = hazirlik_son_zaman()
  for n in range(1, LOGIN_DENEME + 1):
    if n > 1 and simdi() >= son:
      print("Giris zaman siniri doldu.")
      break
    print(f"Giris denemesi {n}/{LOGIN_DENEME}")
    try:
      driver.get(URL)
      time.sleep(3)
      w = WebDriverWait(driver, 20)
      try:
        okudum = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class, 'okudum')]")
            )
        )
        driver.execute_script("arguments[0].click();", okudum)
      except Exception:
        pass
      time.sleep(1)
      u = w.until(EC.presence_of_element_located((By.NAME, "kullanici")))
      u.clear()
      u.send_keys(tc)
      p = driver.find_element(By.NAME, "sifre")
      p.clear()
      p.send_keys(sifre)
      img = w.until(
          EC.presence_of_element_located((By.XPATH, "//img[@class='captcha']"))
      )
      code = captcha_oku(img)
      if not code:
        print("Captcha okunamadi, yenileniyor.")
        continue
      print("Captcha okundu:", code)
      driver.find_element(By.NAME, "code_girisForm").send_keys(code)
      lbtn = w.until(
          EC.presence_of_element_located(
              (By.XPATH, "//button[@type='submit']")
          )
      )
      driver.execute_script("arguments[0].click();", lbtn)
      WebDriverWait(driver, 8).until(
          EC.invisibility_of_element_located((By.NAME, "kullanici"))
      )
      WebDriverWait(driver, 8).until(
          EC.presence_of_element_located(
              (By.XPATH, "//a[contains(., 'Rezervasyon')]")
          )
      )
      print("Giris basarili.")
      return True
    except Exception as e:
      print("Giris hatasi:", type(e).__name__)
  return False


def gece_yarisi_bekle():
  if HEMEN_BASLA:
    print("HEMEN_BASLA aktif, beklenmiyor.")
    return
  print("Saat 00:00 bekleniyor...")
  while True:
    now = simdi()
    if now.hour == 0:
      print("Saat 00:00 basladi!")
      return
    if now.hour not in [22, 23]:
      raise RuntimeError("Gecersiz saat araligi.")
    time.sleep(0.01)


def sonucu_dogrula(driver):
  driver.save_screenshot("sonuc.png")
  try:
    metin = driver.find_element(By.TAG_NAME, "body").text.lower()
  except Exception:
    metin = ""
  if any(k in metin for k in ["dolu", "hata", "yapilamaz", "basarisiz"]):
    return False
  return any(
      k in metin for k in ["basari", "rezervasyonunuz", "tamamlandi", "alindi"]
  )


def hazirlik(driver, w, tc, sifre):
  if not giris_yap(driver, tc, sifre):
    raise RuntimeError("Giris yapilamadi.")
  rmenu = w.until(
      EC.presence_of_element_located(
          (By.XPATH, "//a[contains(., 'Rezervasyon')]")
      )
  )
  driver.execute_script("arguments[0].click();", rmenu)
  kbtn = w.until(
      EC.presence_of_element_located(
          (By.XPATH, "//button[contains(., 'HALUK DURSUN KÜTÜPHANESİ')]")
      )
  )
  driver.execute_script("arguments[0].click();", kbtn)
  s1 = w.until(
      EC.element_to_be_clickable(
          (By.XPATH, f"//a[contains(@data-seans, '{ON_HAZIRLIK_SEANS}')]")
      )
  )
  driver.execute_script("arguments[0].click();", s1)


def rezervasyon_yap(driver, w):
  d = simdi() + timedelta(days=2)
  hedef_tarih = (
      str(d.year)
      + "-"
      + str(d.month).zfill(2)
      + "-"
      + str(d.day).zfill(2)
  )
  url = (
      "https://ktprezervasyon.uskudar.bel.tr/?p=1&dil=0&salon=69&tarih="
      + hedef_tarih
  )
  print("Hedef tarihe gidiliyor:", hedef_tarih)
  driver.get(url)
  time.sleep(2)

  seans_js = "var h=arguments[0]; var y=arguments[1]; var s=document.querySelector('select[name=\"seans\"]'); if(!s) return 'select-yok'; for(var i=0; i<s.options.length; i++){ var t=s.options[i].text; var v=s.options[i].value; if(t.includes(h) || v.includes(h)){ s.selectedIndex=i; s.dispatchEvent(new Event('change')); if(window.jQuery) jQuery(s).trigger('change'); return 'ok'; } } if(s.options.length > y){ s.selectedIndex=y; s.dispatchEvent(new Event('change')); if(window.jQuery) jQuery(s).trigger('change'); return 'yedek:' + s.options[y].text; } return 'bulunamadi';"
  sonuc = driver.execute_script(seans_js, HEDEF_SEANS, YEDEK_INDEX)
  if sonuc.startswith("yedek:"):
    print(f"Yedek seans seçildi: {sonuc[6:]}")
  elif sonuc != "ok":
    raise RuntimeError(f"Seans secilemedi: {sonuc}")

  time.sleep(1.5)

  seat_js = "var sId=arguments[0]; var seat=document.querySelector('span[data-id=\"'+sId+'\"]'); if(!seat) return 'koltuk-yok'; seat.scrollIntoView({block:'center',inline:'center'}); seat.click(); return 'ok';"
  if driver.execute_script(seat_js, KOLTUK) == "koltuk-yok":
    raise RuntimeError("Koltuk bulunamadi.")

  w.until(lambda d: d.find_element(By.CSS_SELECTOR, "button.evet"))
  btn_js = "var b=document.querySelector('button.btn.btn-success.evet') || document.querySelector('button.evet'); if(!b) return 'evet-yok'; b.click(); return 'ok';"
  if driver.execute_script(btn_js) != "ok":
    raise RuntimeError("EVET butonuna basilamadi.")

  time.sleep(2)
  return sonucu_dogrula(driver)


def main():
  tc, sifre = tc_sifre_al()
  opts = Options()
  if HEADLESS:
    opts.add_argument("--headless=new")
  opts.add_argument("--
