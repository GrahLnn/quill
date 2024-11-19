from datetime import datetime
import json
from pathlib import Path

import toml

from src.factory import ScraperFactory


def main():
    # Twitter示例
    url = "https://x.com/GrahLnn/likes"
    scraper = ScraperFactory.get_scraper(
        url,
        browser_path=r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        headless=True,
    )
    try:
        results = scraper.scrape(url)
    finally:
        # scraper.close()
        pass

    # 准备保存数据
    data = {
        "metadata": {
            "url": url,
            "timestamp": datetime.now().isoformat(),
        },
        "results": results,
    }

    # 创建输出目录
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # 生成输出文件名
    output_file = (
        output_dir / f"scrape_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.toml"
    )

    # 保存为toml格式
    with open(output_file, "w", encoding="utf-8") as f:
        toml.dump(data, f)

    # with open(
    #     output_dir / f"scrape_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    #     "w",
    #     encoding="utf-8",
    # ) as f:
    #     json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"数据已保存至: {output_file}")


if __name__ == "__main__":
    main()
