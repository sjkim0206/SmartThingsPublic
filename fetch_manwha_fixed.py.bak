#!/usr/bin/env python3
# -*- coding:utf-8 -*-
import os,re,json,shutil,datetime,traceback,subprocess,requests,xml.etree.ElementTree as ET
from urllib.parse import urljoin,urldefrag
from bs4 import BeautifulSoup,Tag
import holidays
from PIL import Image,ImageStat,ImageFilter

# ===== 설정 =====
BLOG_ID="rlarmrcjs";CATEGORY_NO="31";CATEGORY_NAME="오늘의 신문만평"
BASE_DIR="/sdcard/Pictures/naver_manhwa";SAVE_DIR=os.path.join(BASE_DIR,"downloads");LOG_DIR=os.path.join(BASE_DIR,"logs")
HEADERS={"User-Agent":"Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36","Accept-Language":"ko-KR,ko;q=0.9"}
AD_PATTERNS=["doubleclick","/ad/","/ads/","banner","pixel","tveta","impress","/log","beacon"]
TITLE_RE=re.compile(r"오늘의\s*신문\s*만평\s*\(\s*(\d{4})[년\.\s]*\s*(\d{1,2})[월\.\s]*\s*(\d{1,2})[일\.\s]*",re.U)
NAVER_IMG_HOST_PATTERN=re.compile(r'https?://(?:blogfiles|postfiles|mblogthumb-phinf|blogpfthumb-phinf|blogthumb|post-phinf)\.[a-z0-9\.-]+/[^\s"\'<>]+',re.I)

SIZE_MIN=50*1024

# ===== 카카오톡 전송 설정 =====
KAKAO_ROOMS=["취사","연토91"]
KAKAO_MANIFEST_PATH=os.path.join(BASE_DIR,"kakao_send.json")
KAKAO_TASK_NAME="카톡만평전송"   # Tasker 태스크 이름과 반드시 일치

def log(m):
    os.makedirs(LOG_DIR,exist_ok=True)
    with open(os.path.join(LOG_DIR,f"fetch_{datetime.date.today():%Y-%m-%d}.log"),"a",encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {m}\n")
    print(m)

def today():return datetime.date.today()

def http(u):
    s=requests.Session();s.headers.update(HEADERS)
    r=s.get(u,timeout=25);log(f"[HTTP] GET {r.url}");r.raise_for_status();return r

def parse_title_date(t):
    t=re.sub(r"[\u200b-\u200d\uFEFF]","",t or "").translate(str.maketrans("０１２３４５６７８９","0123456789"))
    m=TITLE_RE.search(t);return (int(m[1]),int(m[2]),int(m[3])) if m else None

def find_post_by_rss(d):
    for su in (f"https://rss.blog.naver.com/{BLOG_ID}.xml?categoryNo={CATEGORY_NO}",f"https://rss.blog.naver.com/{BLOG_ID}.xml"):
        try:
            r=http(su)
            items=ET.fromstring(r.content).findall(".//item")
            for it in items:
                title=(it.findtext("title") or "");link=(it.findtext("link") or "");cat=(it.findtext("category") or "")
                if CATEGORY_NAME not in cat:continue
                ymd=parse_title_date(title)
                if ymd==(d.year,d.month,d.day):
                    if "PostView.naver" not in link:
                        m=re.search(r"/(\d{8,})(?:\?|$)",link)
                        if m:link=f"https://m.blog.naver.com/PostView.naver?blogId={BLOG_ID}&logNo={m[1]}"
                    return link
        except Exception as e:log(f"[WARN] RSS 실패: {e}")
    return ""

def is_ad(u):return (not u) or "data:" in u.lower() or any(p in u.lower() for p in AD_PATTERNS)
def norm(u):
    u=(u or "").strip()
    if u.startswith("//"):u="https:"+u
    u,_=urldefrag(u)
    return u

def extract_dom(html):
    s=BeautifulSoup(html,"html.parser")
    b=s.find(attrs={"class":re.compile(r"(se-main-container|post_view|se_component_wrap)")}) or s
    out=[]
    for n in b.find_all("img"):
        for a in ("data-src","data-lazy-src","data-original","data-origin","data-image-src","src"):
            v=norm(n.get(a));
            if v and not is_ad(v):out.append(v)
        dl=n.get("data-linkdata")
        if dl:
            try:j=json.loads(dl)
            except: j=None
            if j:
                for k in ("originSrc","originUrl","originimgurl","originImageUrl","src","imageSrc"):
                    v=norm(j.get(k))
                    if v and not is_ad(v):out.append(v)
    return [x for i,x in enumerate(out) if x not in out[:i] and not is_ad(x)]

def extract_regex(html):
    u=[]
    for m in NAVER_IMG_HOST_PATTERN.finditer(html):
        v=norm(m.group(0))
        if not is_ad(v):u.append(v)
    return [x for i,x in enumerate(u) if x not in u[:i]]

def expand_candidates(u):
    u=norm(u);base=u.split("?")[0]
    try:
        host=base.split("://",1)[1].split("/",1)[0]
        path=base.split("://",1)[1].split("/",1)[1]
    except Exception:
        return [u]
    prefer_hosts=[]
    if host.startswith("mblogthumb-phinf") or host.startswith("blogthumb"):
        prefer_hosts=["post-phinf.pstatic.net","postfiles.pstatic.net","blogfiles.pstatic.net"]
    elif host.startswith("blogpfthumb-phinf"):
        prefer_hosts=["blogfiles.pstatic.net"]
    else:
        prefer_hosts=[host]
    types=["?type=orig","?type=w1200",""]
    cand=[]
    for h in prefer_hosts:
        for t in types:
            cand.append(f"https://{h}/{path}{t}")
    cand.append(u);cand.append(base)
    out=[];seen=set()
    for c in cand:
        c=norm(c)
        if c and c not in seen:
            seen.add(c);out.append(c)
    return out

def is_thumbnail_like(url:str):
    u=url.lower()
    return ("type=w80" in u) or ("type=w2" in u) or ("w80_blur" in u)

def try_fetch_one(session,url,ref):
    cand=expand_candidates(url)
    head=[c for c in cand if not is_thumbnail_like(c)]
    tail=[c for c in cand if is_thumbnail_like(c)]
    ordered=head+tail
    if ref:session.headers["Referer"]=ref
    best=None;best_size=0;last_err=None
    for x in ordered:
        try:
            r=session.get(x,stream=True,timeout=30)
            if r.status_code!=200:continue
            ctype=(r.headers.get("Content-Type","") or "").lower()
            clen=r.headers.get("Content-Length")
            size=int(clen) if (clen and clen.isdigit()) else None
            body=r.content if (size is None or size<SIZE_MIN) else None
            real_size=(len(body) if body is not None else size) or 0
            if real_size>best_size:
                best=(r,x);best_size=real_size
            if "gif" in ctype and real_size>0:
                return r,x
            if real_size>=SIZE_MIN:
                if body is not None: r._content=body
                return r,x
        except Exception as e:
            last_err=e
            continue
    if best:
        log(f"[FALLBACK] 기준 미달로 최대({best_size} bytes) 파일 사용: {best[1]}")
        return best
    raise RuntimeError(last_err or "no candidate passed SIZE_MIN")

def download_all(urls,folder,ref=None):
    os.makedirs(folder,exist_ok=True)
    out=[];s=requests.Session();s.headers.update(HEADERS)
    for i,u in enumerate(urls,1):
        try:
            r,final=try_fetch_one(s,u,ref)
            ct=(r.headers.get("Content-Type","") or "").lower()
            ext=".jpg";lw=final.lower()
            if "png" in ct or lw.endswith(".png"):ext=".png"
            elif "webp" in ct or lw.endswith(".webp"):ext=".webp"
            elif "gif" in ct or lw.endswith(".gif"):ext=".gif"
            p=os.path.join(folder,f"img_{i:03d}{ext}")
            with open(p,"wb") as f:f.write(r.content)
            out.append(p)
        except Exception as e:
            log(f"[WARN] 다운로드 실패: {u} ({e})")
    return out

def media_scan(targets):
    try:
        t=targets if isinstance(targets,(list,tuple)) else [targets]
        subprocess.run(["termux-media-scan"]+t,check=True)
        log(f"[MEDIA]{t}")
    except Exception as e:
        log(f"[WARN] 미디어 스캔 실패: {e}")

# === 색/여백/엣지 기반 사진 판정(강화) ===
def _entropy(hist):
    try:
        import math
        total=sum(hist)
        if total<=0:return 0.0
        probs=[x/total for x in hist if x>0]
        return -sum(p*math.log(p,2) for p in probs)
    except Exception:
        return 0.0

def is_photo_image(path:str)->bool:
    try:
        img=Image.open(path).convert("RGB")
        base_w=640
        if img.width>base_w:
            h=int(img.height*base_w/img.width); img=img.resize((base_w,h))
        w,h=img.size
        ratio=w/h if h>0 else 1.0

        stat=ImageStat.Stat(img)
        mean_rgb=[c/255.0 for c in stat.mean]
        std_rgb=[c/255.0 for c in stat.stddev]
        mean=sum(mean_rgb)/3.0
        stddev=sum(std_rgb)/3.0

        hsv=img.convert("HSV"); hist=hsv.histogram()
        h_hist=hist[0:256]; s_hist=hist[256:512]; v_hist=hist[512:768]
        ent_h=_entropy(h_hist); ent_s=_entropy(s_hist); ent_v=_entropy(v_hist)
        color_entropy=ent_h+ent_s+ent_v

        v_vals=v_hist
        v_total=sum(v_vals) or 1
        white_ratio=sum(v_vals[int(0.85*255):])/v_total
        dark_ratio=sum(v_vals[:int(0.1*255)])/v_total

        edges=img.convert("L").filter(ImageFilter.FIND_EDGES)
        edge_mean=ImageStat.Stat(edges).mean[0]/255.0

        cartoon_guard=False
        if dark_ratio>0.015 and white_ratio>0.12:
            cartoon_guard=True
        if edge_mean>0.12 and 0.7<=ratio<=1.35:
            cartoon_guard=True
        if color_entropy<14.5 and edge_mean>0.09:
            cartoon_guard=True
        if cartoon_guard:
            log(f"[PHOTO?GUARD] keep {os.path.basename(path)} edge={edge_mean:.3f} white={white_ratio:.3f} dark={dark_ratio:.3f} ent={color_entropy:.2f} mean={mean:.2f} std={stddev:.3f} r={ratio:.2f}")
            return False

        suspicious=0
        if ratio>1.65 or ratio<0.55: suspicious+=1
        if 0.35<mean<0.70: suspicious+=1
        if stddev<0.06: suspicious+=1
        if color_entropy>17.5: suspicious+=1
        if edge_mean<0.07: suspicious+=1
        if white_ratio<0.06 and dark_ratio<0.008: suspicious+=1

        is_photo = suspicious>=3
        log(f"[PHOTO?EVAL] {'PHOTO' if is_photo else 'KEEP'} {os.path.basename(path)} s={suspicious} edge={edge_mean:.3f} white={white_ratio:.3f} dark={dark_ratio:.3f} ent={color_entropy:.2f} mean={mean:.2f} std={stddev:.3f} r={ratio:.2f}")
        return is_photo
    except Exception as e:
        log(f"[WARN] 사진 판정 실패: {path} ({e})")
        return False

# ===== 카카오톡 전송 =====
def send_to_kakao(files:list):
    if not files:
        log("[KAKAO] 전송할 파일 없음");return

    manifest={
        "files": files,
        "rooms": KAKAO_ROOMS,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(KAKAO_MANIFEST_PATH,"w",encoding="utf-8") as f:
            json.dump(manifest,f,ensure_ascii=False,indent=2)
        log(f"[KAKAO] manifest 저장 완료: {KAKAO_MANIFEST_PATH} ({len(files)}개 파일)")
    except Exception as e:
        log(f"[KAKAO][ERR] manifest 저장 실패: {e}");return

    try:
        result=subprocess.run(
            [
                "am","broadcast",
                "-a","net.dinglisch.android.taskerm.ACTION_TASK",
                "--es","task_name",KAKAO_TASK_NAME,
                "--ez","TASK_IF_COLLISION_ABORT","false"
            ],
            capture_output=True,text=True,timeout=10
        )
        if result.returncode==0:
            log(f"[KAKAO] Tasker 태스크 '{KAKAO_TASK_NAME}' 트리거 성공")
        else:
            log(f"[KAKAO][WARN] Tasker 트리거 반환값={result.returncode}: {result.stderr.strip()}")
            _fallback_share(files)
    except FileNotFoundError:
        log("[KAKAO][WARN] am 명령 없음 → termux-share 대체")
        _fallback_share(files)
    except Exception as e:
        log(f"[KAKAO][ERR] Tasker 트리거 예외: {e}")
        _fallback_share(files)

def _fallback_share(files:list):
    log("[KAKAO][FALLBACK] termux-share로 파일 공유 시작")
    for f in files:
        try:
            subprocess.run(["termux-share","-a","send",f],timeout=30)
            log(f"[KAKAO][FALLBACK] 공유: {os.path.basename(f)}")
        except Exception as e:
            log(f"[KAKAO][FALLBACK][WARN] 공유 실패: {f} ({e})")

def main():
    d=today();log("===== 실행 시작 =====")
    if d.weekday()==6 or d in holidays.SouthKorea():log("휴일/일요일");return
    post=find_post_by_rss(d)
    if not post:log("오늘 글 없음");return
    log(f"[INFO]{post}")
    html=[]
    try:html.append(http(post).text)
    except Exception as e:log(f"[WARN] 모바일 본문 실패: {e}")
    try:
        pc=post.replace("m.blog.naver.com","blog.naver.com")
        pc_html=http(pc).text;html.append(pc_html)
        s=BeautifulSoup(pc_html,"html.parser")
        f=s.find("iframe")
        if f and f.get("src"):
            html.append(http(urljoin("https://blog.naver.com",f["src"])).text)
    except Exception as e:log(f"[WARN] PC 본문 실패: {e}")
    try:
        logno=re.search(r"logNo=(\d+)",post).group(1)
        direct=f"https://blog.naver.com/PostView.naver?blogId={BLOG_ID}&logNo={logno}&redirect=Dlog&widgetTypeCall=true&directAccess=true"
        html.append(http(direct).text)
    except Exception as e:log(f"[WARN] directAccess 실패: {e}")
    urls=[]
    for h in html:urls+=extract_dom(h)
    for h in html:urls+=extract_regex(h)
    urls=[x for i,x in enumerate(urls) if x not in urls[:i] and not is_ad(x)]
    if not urls:log("이미지 없음");return
    folder=os.path.join(SAVE_DIR,f"{d:%Y-%m-%d}")
    if os.path.isdir(folder):shutil.rmtree(folder)
    saved=download_all(urls,folder,ref=post)
    if not saved:log("저장 실패");return
    try:
        seen_sizes={}
        for fn in list(sorted(os.listdir(folder))):
            fp=os.path.join(folder,fn)
            if not os.path.isfile(fp):continue
            try:
                sz=os.path.getsize(fp)
                if sz in seen_sizes:
                    os.remove(fp)
                    log(f"[CLEAN] 동일 사이즈 중복 삭제: {fp} (size={sz})")
                else:
                    seen_sizes[sz]=fp
            except Exception as e:
                log(f"[WARN] 중복 제거 중 오류: {fp} ({e})")
        for fn in list(sorted(os.listdir(folder))):
            fp=os.path.join(folder,fn)
            if not os.path.isfile(fp):continue
            if is_photo_image(fp):
                os.remove(fp)
                log(f"[CLEAN] 사진으로 판정되어 삭제됨: {fp}")
    except Exception as e:
        log(f"[WARN] 정리 단계 오류: {e}")
    media_scan(folder)
    try:
        files=[os.path.join(folder,x) for x in sorted(os.listdir(folder)) if os.path.isfile(os.path.join(folder,x))]
        if files:
            os.remove(files[-1]);log(f"last{files[-1]}")
    except Exception as e:
        log(f"[WARN] 마지막 1장 삭제 실패: {e}")
    media_scan(folder)

    try:
        final_files=[
            os.path.join(folder,x)
            for x in sorted(os.listdir(folder))
            if os.path.isfile(os.path.join(folder,x))
        ]
        send_to_kakao(final_files)
    except Exception as e:
        log(f"[WARN] 카카오톡 전송 실패: {e}")

    log(f"완료:{folder}")

if __name__=="__main__":
    try:main()
    except Exception as e:log("치명 오류: "+str(e))
