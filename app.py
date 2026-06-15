"""Hello World Flask Application."""
import os
from flask import Flask

app = Flask(__name__)


@app.route('/')
def index():
    """Return the hello world page."""
    return (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="UTF-8"><title>Hi World</title>'
        '<style>body{display:flex;justify-content:center;'
        'align-items:center;height:100vh;margin:0;}</style>'
        '</head><body><h1>hiworld</h1></body></html>'
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5008))
    app.run(host='0.0.0.0', port=port)
