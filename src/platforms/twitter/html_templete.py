FULL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Tweets Gallery</title>
    <link rel="icon" type="image/png" href="{favicon_path}">
    <style>{html_styles}</style>
    <script type="module">
        {script}
    </script>
</head>
  <body>
    <div class="toolbar">
      <nav class="nav" data-orientation="horizontal">
        <ul>
          <li id="translate-button">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 18 18"
            >
              <g
                fill="none"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="1.5"
                stroke="#212121"
              >
                <path d="M2.25 4.25H10.25"></path>
                <path d="M6.25 2.25V4.25"></path>
                <path d="M4.25 4.25C4.341 6.926 6.166 9.231 8.75 9.934"></path>
                <path d="M8.25 4.25C7.85 9.875 2.25 10.25 2.25 10.25"></path>
                <path d="M9.25 15.75L12.25 7.75H12.75L15.75 15.75"></path>
                <path d="M10.188 13.25H14.813"></path>
              </g>
            </svg>
          </li>
          <li>
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 18 18"
            >
              <g fill="#212121">
                <path
                  opacity="0.4"
                  d="M12.7501 9.75H5.25009C4.83599 9.75 4.50009 9.4141 4.50009 9C4.50009 8.5859 4.83599 8.25 5.25009 8.25H12.7501C13.1642 8.25 13.5001 8.5859 13.5001 9C13.5001 9.4141 13.1642 9.75 12.7501 9.75Z"
                ></path>
                <path
                  d="M15.2501 5H2.75009C2.33599 5 2.00009 4.6641 2.00009 4.25C2.00009 3.8359 2.33599 3.5 2.75009 3.5H15.2501C15.6642 3.5 16.0001 3.8359 16.0001 4.25C16.0001 4.6641 15.6642 5 15.2501 5Z"
                ></path>
                <path
                  d="M10.0001 14.5H8.00009C7.58599 14.5 7.25009 14.1641 7.25009 13.75C7.25009 13.3359 7.58599 13 8.00009 13H10.0001C10.4142 13 10.7501 13.3359 10.7501 13.75C10.7501 14.1641 10.4142 14.5 10.0001 14.5Z"
                ></path>
              </g>
            </svg>
          </li>
          <li>
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 18 18"
            >
              <g fill="#212121">
                <path
                  opacity="0.4"
                  d="M14.146 6.32703C13.704 3.86403 11.535 2 9 2C6.105 2 3.75 4.355 3.75 7.25C3.75 7.378 3.755 7.50801 3.767 7.64001C2.163 8.07101 1 9.525 1 11.25C1 13.318 2.682 15 4.75 15H12.5C14.981 15 17 12.981 17 10.5C17 8.646 15.85 6.99703 14.146 6.32703Z"
                ></path>
                <path
                  d="M11.78 10.031L9.52999 12.281C9.38399 12.427 9.19199 12.501 8.99999 12.501C8.80799 12.501 8.61599 12.428 8.46999 12.281L6.21999 10.031C5.92699 9.73801 5.92699 9.26297 6.21999 8.96997C6.51299 8.67697 6.98799 8.67697 7.28099 8.96997L8.25099 9.94V6.75098C8.25099 6.33698 8.58699 6.00098 9.00099 6.00098C9.41499 6.00098 9.75099 6.33698 9.75099 6.75098V9.94L10.721 8.96997C11.014 8.67697 11.489 8.67697 11.782 8.96997C12.075 9.26297 12.075 9.73801 11.782 10.031H11.78Z"
                ></path>
              </g>
            </svg>
          </li>
        </ul>
      </nav>
      <div class="flex-col">
        <span class="timestamp">{create_time}</span>
        <span class="timestamp">{item}</span>
      </div>
    </div>

    <div class="tip" aria-hidden="true">
      <div class="tip__track">
        <div>Show Translation</div>
        <div>Filter Content</div>
        <div>Download Resources</div>
      </div>
    </div>
    <main class="main-container">
      <div class="tweets-container">
        <div class="tweets-column"></div>
        <div class="tweets-column"></div>
        <div class="tweets-column"></div>
      </div>
    </main>
  </body>
</html>
"""