"""Draw diagnostic cell boxes over an existing PDF page render."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import read_json


if __name__=='__main__':
    from PIL import Image,ImageDraw
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--page-image',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();data=read_json(args.evidence)
    page=Image.open(args.page_image).convert('RGB');draw=ImageDraw.Draw(page)
    sx=page.width/data['page_dimensions']['width'];sy=page.height/data['page_dimensions']['height']
    for cell in data['cells']:
        x0,y0,x1,y1=cell['bbox'];color='red' if cell['issues'] else '#1766cc'
        draw.rectangle([x0*sx,y0*sy,x1*sx,y1*sy],outline=color,width=2)
    args.output.parent.mkdir(parents=True,exist_ok=True);page.save(args.output)
