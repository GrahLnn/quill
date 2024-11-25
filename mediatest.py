from DrissionPage import SessionPage
import json


def get_twitter_video_info(url):
    # 创建SessionPage对象
    page = SessionPage()

    # 访问Twitter链接
    result = page.get(url)
    if not result:
        print("Failed to access the page")
        return None

    # 打印页面标题和URL信息
    print(f"Page Title: {page.title}")
    print(f"Current URL: {page.url}")

    # 尝试获取页面的JSON数据
    try:
        # 查找包含视频信息的script标签
        scripts = page.eles('script[type="application/json"]')

        for script in scripts:
            try:
                content = script.inner_text
                if content:
                    data = json.loads(content)
                    print(json.dumps(data, indent=4, ensure_ascii=False))
                    # 在JSON数据中查找视频URL
                    if "video_info" in str(data):
                        print("Found video information in JSON data")
                        return data
            except json.JSONDecodeError:
                continue

        print("No video information found in the page")
        return None

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return None


# 测试代码
if __name__ == "__main__":
    url = "https://x.com/i/status/1858513730604015960"
    video_info = get_twitter_video_info(url)
    if video_info:
        print("Successfully retrieved video information")
