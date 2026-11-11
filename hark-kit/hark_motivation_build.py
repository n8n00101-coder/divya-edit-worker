import os, subprocess, random, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
os.chdir('/workspace/work/mv')
W,H=1080,1920
NB='/usr/share/fonts/opentype/urw-base35/NimbusSansNarrow-Bold.otf'
DB='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
Y=(245,197,24); WH=(235,235,235); GR=(140,140,140)
def F(p,s): return ImageFont.truetype(p,s)
env={k:v for k,v in os.environ.items() if 'proxy' not in k.lower()}

scenes=[
 dict(say="Motivation fades in three days.", head="MOTIVATION", sub="FADES IN 3 DAYS", g="battery", cap=[("Motivation",1),(" fades in three days.",0)], col=(20,22,40)),
 dict(say="Discipline still shows up on day three hundred.", head="DISCIPLINE", sub="SHOWS UP ON", g="cal", cap=[("Discipline",1),(" shows up on day 300.",0)], col=(30,20,36)),
 dict(say="Nobody sees your five A M alarm.", head="NOBODY SEES", sub="", g="clock", cap=[("Nobody",1),(" sees your 5 AM alarm.",0)], col=(14,24,34)),
 dict(say="They only see the result.", head="THEY ONLY SEE", sub="THE RESULT", g="bars", cap=[("They only see the ",0),("result.",1)], col=(32,26,14)),
 dict(say="Get just one percent better every day.", head="1%", sub="BETTER EVERY DAY", g="none", cap=[("One percent",1),(" better every day.",0)], col=(16,28,22)),
 dict(say="In one year, that's thirty seven times better.", head="37x", sub="IN ONE YEAR", g="curve", cap=[("That's ",0),("37 times",1),(" better.",0)], col=(34,16,26), src="Math: 1.01 ^ 365 = 37.8"),
 dict(say="So start today. Not Monday.", head="START TODAY.", sub="MONDAY", g="strike", cap=[("Start ",0),("today.",1),(" Not Monday.",0)], col=(12,12,14)),
]

def bg(col):
    im=Image.new('RGB',(W,H),(10,10,12))
    d=ImageDraw.Draw(im)
    for r in range(1100,0,-20):
        t=r/1100
        c=tuple(int(10+(col[i]*2.2-10)*(1-t)) for i in range(3))
        d.ellipse([W/2-r,H*0.42-r,W/2+r,H*0.42+r],fill=c)
    im=im.filter(ImageFilter.GaussianBlur(40))
    d=ImageDraw.Draw(im)
    random.seed(len(str(col)))
    for _ in range(9000):
        x,y=random.randrange(W),random.randrange(H); v=random.randrange(25,60)
        d.point((x,y),fill=(v,v,v))
    for x in range(0,W,90): d.line([x,0,x,H],fill=(255,255,255,12) if False else (28,28,32),width=1)
    for y in range(0,H,90): d.line([0,y,W,y],fill=(28,28,32),width=1)
    return im

def ctext(d,y,txt,font,fill):
    w=d.textlength(txt,font=font); d.text(((W-w)/2,y),txt,font=font,fill=fill)

def graphic(d,g,im):
    cx,cy=W//2,880
    if g=="battery":
        d.rounded_rectangle([cx-230,cy-120,cx+210,cy+120],20,outline=WH,width=12)
        d.rectangle([cx+215,cy-45,cx+250,cy+45],fill=WH)
        d.rectangle([cx-205,cy-95,cx-120,cy+95],fill=(220,60,50))
    elif g=="cal":
        d.rounded_rectangle([cx-200,cy-200,cx+200,cy+200],24,fill=(240,240,240))
        d.rounded_rectangle([cx-200,cy-200,cx+200,cy-90],24,fill=(220,50,50)); d.rectangle([cx-200,cy-120,cx+200,cy-90],fill=(220,50,50))
        ctext(d,cy-190,"DAY",F(NB,80),WH); ctext(d,cy-75,"300",F(NB,230),(20,20,20))
    elif g=="clock":
        d.ellipse([cx-230,cy-230,cx+230,cy+230],outline=WH,width=12)
        for i in range(12):
            a=i*math.pi/6; d.line([cx+200*math.sin(a),cy-200*math.cos(a),cx+225*math.sin(a),cy-225*math.cos(a)],fill=WH,width=8)
        d.line([cx,cy,cx,cy-170],fill=Y,width=12); d.line([cx,cy,cx+5*0+130*math.sin(5*math.pi/6),cy-130*math.cos(5*math.pi/6)],fill=WH,width=14)
        d.ellipse([cx-18,cy-18,cx+18,cy+18],fill=Y)
        ctext(d,cy+260,"5:00 AM",F(NB,110),Y)
    elif g=="bars":
        hs=[60,90,70,120,100,160,140,220,300,420]
        for i,h in enumerate(hs):
            x=cx-350+i*72; c=Y if i==len(hs)-1 else (90,90,95)
            d.rectangle([x,cy+250-h,x+52,cy+250],fill=c)
        d.line([cx-380,cy+260,cx+380,cy+260],fill=WH,width=6)
    elif g=="curve":
        pts=[(cx-380+i*7.6, cy+250-((1.01**(i*3.65))-1)/36.8*480) for i in range(101)]
        d.line([cx-380,cy+260,cx+400,cy+260],fill=WH,width=5); d.line([cx-380,cy+260,cx-380,cy-260],fill=WH,width=5)
        d.line(pts,fill=Y,width=12); x,y=pts[-1]; d.ellipse([x-20,y-20,x+20,y+20],fill=Y)
        d.text((cx-370,cy+280),"DAY 1",font=F(NB,50),fill=GR); d.text((cx+230,cy+280),"DAY 365",font=F(NB,50),fill=GR)

def make(i,s):
    im=bg(s['col']); d=ImageDraw.Draw(im)
    d.rectangle([60,110,68,160],fill=Y); d.text((85,108),"BLIND WORLD",font=F(DB,44),fill=WH)
    if s['head'] in ("1%","37x"):
        ctext(d,560 if s['g']=="none" else 260,s['head'],F(NB,520 if s['g']=="none" else 300),Y)
        ctext(d,1160 if s['g']=="none" else 1260,s['sub'],F(NB,110),WH)
    elif s['g']=="strike":
        ctext(d,600,"START",F(NB,260),WH); ctext(d,860,"TODAY.",F(NB,260),Y)
        f=F(NB,130); w=d.textlength("MONDAY",font=f); ctext(d,1200,"MONDAY",f,GR)
        d.line([(W-w)/2-20,1275,(W+w)/2+20,1265],fill=(220,50,50),width=14)
    else:
        ctext(d,300,s['head'],F(NB,170),WH)
        if s['sub'] and s['g'] not in ("bars",): ctext(d,480,s['sub'],F(NB,90),Y)
        if s['g']=="bars": ctext(d,480,s['sub'],F(NB,110),Y)
    graphic(d,s['g'],im)
    if s.get('src'):
        d.rectangle([60,1500,66,1532],fill=Y); d.text((80,1500),s['src'],font=F(DB,28),fill=GR)
    f=F(DB,58); tw=sum(d.textlength(t,font=f) for t,_ in s['cap'])
    x=(W-tw)/2; y=1600
    for t,hl in s['cap']:
        d.text((x,y),t,font=f,fill=Y if hl else WH); x+=d.textlength(t,font=f)
    ctext(d,1700,"B L I N D   W O R L D",F(DB,30),GR)
    im.save(f'sc{i}.png')

parts=[]
for i,s in enumerate(scenes):
    make(i,s)
    subprocess.run(['python3','-m','edge_tts','--voice','en-US-ChristopherNeural','--rate=-8%','--pitch=-4Hz','--text',s['say'],'--write-media',f'v{i}.mp3'],env=env,check=True,capture_output=True)
    dur=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f'v{i}.mp3']))+0.45
    vf=f"scale=w='1080*(1+0.06*t/{dur:.2f})':h=-2:eval=frame,crop=1080:1920,fade=in:st=0:d=0.25,fade=out:st={dur-0.25:.2f}:d=0.25,format=yuv420p"
    subprocess.run(['ffmpeg','-v','error','-y','-loop','1','-framerate','30','-t',f'{dur:.2f}','-i',f'sc{i}.png','-i',f'v{i}.mp3',
      '-filter_complex',f"[0:v]{vf}[v];[1:a]apad,atrim=0:{dur:.2f},aresample=44100,aformat=channel_layouts=stereo[a]",
      '-map','[v]','-map','[a]','-c:v','libx264','-preset','veryfast','-crf','20','-r','30','-c:a','aac','-b:a','128k',f'p{i}.mp4'],check=True)
    parts.append(f'p{i}.mp4')
open('list.txt','w').write(''.join(f"file '{p}'\n" for p in parts))
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i','list.txt','-c','copy','cat.mp4'],check=True)
T=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0','cat.mp4']))
# soft ambient pad underneath
subprocess.run(['ffmpeg','-v','error','-y','-i','cat.mp4','-f','lavfi','-t',f'{T:.2f}','-i',
  "aevalsrc='0.05*sin(2*PI*110*t)+0.035*sin(2*PI*164.8*t)+0.03*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*0.25*t))':s=44100:c=stereo",
  '-filter_complex',f"[1:a]afade=in:d=1.5,afade=out:st={T-1.5:.2f}:d=1.5[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1[a]",
  '-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','160k','-movflags','+faststart','/workspace/work/mv/BlindWorld_Motivation_Short.mp4'],check=True)
print(T)
