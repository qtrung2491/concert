import os
import re
import requests
from flask import Flask
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "DÁN_TOKEN_VÀO_ĐÂY_NẾU_TEST_MÁY_TÍNH")
CHAT_ID = os.environ.get("CHAT_ID", "DÁN_CHAT_ID_VÀO_ĐÂY_NẾU_TEST_MÁY_TÍNH")

# 1. DANH SÁCH RSS XML TỪ RSS.APP CỦA BẠN + GOOGLE NEWS
RSS_FEEDS = [
    "https://rss.app/feeds/ueYyZE3XDFrpiz8v.xml",
    "https://rss.app/feeds/IOCugb5xQ4jhlCpm.xml",
    "https://rss.app/feeds/ltg3aRjWP5UKNxHK.xml",
    "https://rss.app/feeds/ISMKuWulzjaqRGbI.xml",
    "https://news.google.com/rss/search?q=%22n%E1%BB%91i+v%C3%B2ng+tay+l%E1%BB%9Bn%22+th%C3%A1i+nguy%C3%AAn+v%C3%A9&hl=vi&gl=VN&ceid=VN:vi"
]

# 2. DANH SÁCH FANPAGE FACEBOOK QUÉT KÉP TRỰC TIẾP
FB_PAGES = [
    "https://www.facebook.com/thainguyenpage",
    "https://www.facebook.com/profile.php?id=61593830150754",
    "https://www.facebook.com/tuhaolanguoivietnam.info",
    "https://www.facebook.com/Review24h"
]

# 3. WEBSITE BÁO CHÍ ĐỊA PHƯƠNG
WEB_URLS = [
    "https://thainguyentv.vn/",
    "https://baothainguyen.vn/"
]

# BỘ LỌC KÉP CHỐNG LAN MAN: Phải có ít nhất 1 từ khóa Sự kiện + 1 từ khóa Vé/Link
EVENT_KEYWORDS = [
    "nối vòng tay lớn", "tự hào là người việt nam", 
    "concert quốc gia", "concert thái nguyên", "âm vang tổ quốc"
]

TICKET_KEYWORDS = [
    "vé", "đăng ký", "mở cổng", "link", "biểu mẫu", 
    "forms.gle", "docs.google.com", "bit.ly", "qr", "nhận vé", "phát vé"
]

seen_items = set()
is_first_run = True  # Cờ đánh dấu lần chạy đầu tiên để không spam bài cũ

def is_relevant_post(text):
    """Kiểm tra bài viết có thực sự nói về VÉ của CONCERT không"""
    text_lower = text.lower()
    has_event = any(ek in text_lower for ek in EVENT_KEYWORDS)
    has_ticket = any(tk in text_lower for tk in TICKET_KEYWORDS)
    # Nếu trong bài có thẳng link Google Form thì báo luôn không cần hỏi nhiều
    has_direct_form = any(fl in text_lower for fl in ["forms.gle", "docs.google.com/forms"])
    
    return (has_event and has_ticket) or has_direct_form

def send_telegram_alert(source, text, link):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # Lọc riêng link form đăng ký nếu có
    form_links = re.findall(r'(https?://(?:forms\.gle|docs\.google\.com/forms|bit\.ly|tinyurl\.com|t\.ly)[^\s"<>]+)', text)
    form_alert = ""
    if form_links:
        clean_links = "\n".join(set(form_links))
        form_alert = f"\n\n🔥 <b>LINK ĐĂNG KÝ TRỰC TIẾP:</b>\n{clean_links}"

    safe_text = text.replace("<", "&lt;").replace(">", "&gt;")
    msg = (
        f"🚨 <b>CÓ THÔNG TIN VÉ MỚI ({source})!</b>\n\n"
        f"📝 <b>Nội dung:</b> {safe_text[:350]}...\n\n"
        f"🔗 <b>Xem bài gốc:</b> {link}"
        f"{form_alert}"
    )
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")

def scan_all_sources(silent_mode=False):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0"}
    new_count = 0

    # 1. Quét RSS.app & Google News
    for rss_url in RSS_FEEDS:
        try:
            resp = requests.get(rss_url, headers=headers, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "xml")
            channel_title = soup.find("title").text if soup.find("title") else "Fanpage"

            for item in soup.find_all("item"):
                title = item.title.text if item.title else ""
                desc_html = item.description.text if item.description else ""
                link = item.link.text.strip() if item.link else ""

                desc_soup = BeautifulSoup(desc_html, "html.parser")
                extracted_urls = " ".join([a["href"] for a in desc_soup.find_all("a", href=True)])
                clean_desc = " ".join(desc_soup.get_text().split())
                full_text = f"{title} - {clean_desc} {extracted_urls}".strip()
                
                item_id = link if link else f"RSS_{full_text[:80]}"

                if is_relevant_post(full_text):
                    if item_id not in seen_items:
                        seen_items.add(item_id)
                        if not silent_mode:
                            send_telegram_alert(channel_title[:25], f"{title}\n{clean_desc}", link)
                            new_count += 1
        except Exception as e:
            print(f"Lỗi RSS {rss_url}: {e}")

    # 2. Quét trực tiếp Facebook Plugin
    for page_url in FB_PAGES:
        try:
            encoded_url = quote(page_url, safe='')
            plugin_url = f"https://www.facebook.com/plugins/page.php?href={encoded_url}&tabs=timeline&width=500&height=800"
            resp = requests.get(plugin_url, headers=headers, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for post in soup.find_all("div", class_=re.compile(r"text_exposed_root|_5pbx|userContent")):
                links_in_post = " ".join([a["href"] for a in post.find_all("a", href=True)])
                content = " ".join(post.get_text().split())
                if not content:
                    continue
                full_content = f"{content} {links_in_post}"
                post_id = f"FB_{content[:80]}"

                if is_relevant_post(full_content):
                    if post_id not in seen_items:
                        seen_items.add(post_id)
                        if not silent_mode:
                            send_telegram_alert("Facebook Page", content, page_url)
                            new_count += 1
        except Exception as e:
            print(f"Lỗi FB {page_url}: {e}")

    # 3. Quét Báo Thái Nguyên
    for base_url in WEB_URLS:
        try:
            resp = requests.get(base_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                title = " ".join(a_tag.get_text().split())
                if len(title) < 10:
                    continue
                full_url = urljoin(base_url, a_tag["href"])
                if is_relevant_post(title):
                    if full_url not in seen_items:
                        seen_items.add(full_url)
                        if not silent_mode:
                            send_telegram_alert("Báo Thái Nguyên", title, full_url)
                            new_count += 1
        except Exception as e:
            print(f"Lỗi Web {base_url}: {e}")

    return new_count

@app.route("/")
def run_scanner():
    global is_first_run
    if is_first_run:
        # Lần chạy đầu tiên: Quét âm thầm để nạp toàn bộ bài cũ vào bộ nhớ, không gửi thông báo rác
        scan_all_sources(silent_mode=True)
        is_first_run = False
        
        # Chỉ gửi 1 tin nhắn duy nhất báo hiệu hệ thống đã bắt đầu canh bài mới
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        welcome_msg = (
            f"✅ <b>BOT CANH VÉ CONCERT ĐÃ KÍCH HOẠT!</b>\n"
            f"📌 Đã nạp và bỏ qua <b>{len(seen_items)}</b> bài viết cũ.\n"
            f"⚡ Từ giây phút này, chỉ khi nào Fanpage hoặc Báo đăng bài MỚI TINH về vé thì bot mới báo cho bạn!"
        )
        requests.post(url, json={"chat_id": CHAT_ID, "text": welcome_msg, "parse_mode": "HTML"}, timeout=10)
        return f"Khởi tạo thành công! Đã bỏ qua {len(seen_items)} bài cũ. Đang rình bài mới...", 200
    else:
        # Các lần chạy sau (mỗi 1 phút): Có bài mới nào khớp bộ lọc kép là bắn về Telegram ngay!
        new_count = scan_all_sources(silent_mode=False)
        return f"✅ Đã quét xong! Tin mới phát hiện: {new_count} | Đang nhớ: {len(seen_items)} bài.", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)