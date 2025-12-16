def get_email_html_template(title, content, button_text, button_url, logo_url):
    """Generate HTML email template with consistent styling"""
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #ffffff; margin: 0; padding: 0; }}
      .container {{ background-color: #fafafa; width: 100%; max-width: 448px; border-radius: 16px; padding: 40px; text-align: center; margin: 40px auto; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1); }}
      .logo {{ display: flex; justify-content: center; align-items: center; gap: 8px; margin-bottom: 24px; }}
      .logo img {{ width: 120px; height: auto; }}
      h1 {{ font-size: 24px; font-weight: 600; margin: 0 0 8px 0; color: #000000; }}
      p {{ color: #6b7280; margin: 0 0 24px 0; font-size: 14px; white-space: pre-wrap; }}
      .button {{ display: inline-block; background-color: #000000; color: #ffffff; padding: 8px 24px; border-radius: 8px; font-weight: 500; text-decoration: none; transition: background-color 0.2s; }}
      .button:hover {{ background-color: #1f2937; }}
    </style>
  </head>
  <body>
    <div class="container">
      <div class="logo">
        <img src="{logo_url}" alt="journies.ai logo" />
      </div>
      <h1>{title}</h1>
      <p>{content}</p>
      <a href="{button_url}" class="button">{button_text}</a>
    </div>
  </body>
</html>"""
