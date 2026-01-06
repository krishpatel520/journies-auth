import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def get_email_html_template(title, content, button_text, button_url, logo_url=None, subtitle=None):
    """Generate HTML email template with logo URL"""
    logo_html = ''
    
    if logo_url:
        logo_html = f'<img src="{logo_url}" alt="Journies logo" style="width: 120px; height: auto; display: block;" />'
        logger.info(f"Using logo URL: {logo_url}")
    
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #ffffff; margin: 0; padding: 0; }}
      .container {{ background-color: #fafafa; width: 100%; max-width: 448px; border-radius: 16px; padding: 40px; text-align: center; margin: 40px auto; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1); }}
      .logo {{ display: block; text-align: center; margin-bottom: 24px; }}
      h1 {{ font-size: 24px; font-weight: 600; margin: 0 0 8px 0; color: #000000; }}
      h4 {{ font-size: 14px; font-weight: 400; margin: 0 0 24px 0; color: #6b7280; }}
      p {{ color: #6b7280; margin: 0 0 24px 0; font-size: 14px; line-height: 1.5; }}
      .button {{ display: inline-block; background-color: #000000; color: #ffffff; padding: 12px 32px; border-radius: 8px; font-weight: 500; text-decoration: none; transition: background-color 0.2s; font-size: 16px; }}
      .button:hover {{ background-color: #1f2937; }}
    </style>
  </head>
  <body>
    <div class="container">
      <div class="logo">
        {logo_html}
      </div>
      <h1>{title}</h1>
      {f'<h4>{subtitle}</h4>' if subtitle else ''}
      <p>{content}</p>
      <a href="{button_url}" class="button">{button_text}</a>
    </div>
  </body>
</html>"""
