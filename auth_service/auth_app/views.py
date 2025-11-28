from django.shortcuts import render
from django.http import HttpResponse
from django.conf import settings
import os

def index(request):
    return render(request, 'index.html')

def email_files_list(request):
    """List email files in readable HTML format"""
    files = os.listdir(settings.EMAIL_FILES_DIR)
    html = '<html><body><h1>Email Files</h1><ul>'
    for filename in sorted(files):
        if os.path.isfile(os.path.join(settings.EMAIL_FILES_DIR, filename)):
            html += f'<li><a href="{filename}">{filename}</a></li>'
    html += '</ul></body></html>'
    return HttpResponse(html)

def email_file_detail(request, filename):
    """Serve individual email file"""
    filepath = os.path.join(settings.EMAIL_FILES_DIR, filename)
    if not os.path.isfile(filepath):
        return HttpResponse('File not found', status=404)
    with open(filepath, 'r') as f:
        return HttpResponse(f'<pre>{f.read()}</pre>')
