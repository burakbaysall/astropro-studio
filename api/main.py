from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional
import os
import swisseph as swe
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim

app = FastAPI(title="AstroPro Swiss Ephemeris API")
origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS","https://burakbaysall.github.io").split(",") if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=["POST","GET"],allow_headers=["Content-Type"])
geocoder=Nominatim(user_agent="astropro-studio-mvp/1.0")
tzfinder=TimezoneFinder()
BODIES={"Sun":swe.SUN,"Moon":swe.MOON,"Mercury":swe.MERCURY,"Venus":swe.VENUS,"Mars":swe.MARS,"Jupiter":swe.JUPITER,"Saturn":swe.SATURN,"Uranus":swe.URANUS,"Neptune":swe.NEPTUNE,"Pluto":swe.PLUTO}
SIGNS=["Koç","Boğa","İkizler","Yengeç","Aslan","Başak","Terazi","Akrep","Yay","Oğlak","Kova","Balık"]
class ChartRequest(BaseModel):
    name: str=Field(min_length=1,max_length=120)
    date: str
    place: str=Field(min_length=2,max_length=200)
    time: Optional[str]=None
    latitude: Optional[float]=Field(default=None,ge=-90,le=90)
    longitude: Optional[float]=Field(default=None,ge=-180,le=180)
    timezone: Optional[str]=None

@app.get("/health")
def health():return {"ok":True,"engine":"Swiss Ephemeris","version":swe.version}

@app.post("/chart")
def chart(req:ChartRequest):
    try:
        y,m,d=map(int,req.date.split("-"))
        hour,minute=(map(int,req.time.split(":")) if req.time else (12,0))
        local=datetime(y,m,d,hour,minute)
        if not 1800<=y<=2399:raise ValueError("Desteklenen yıl aralığı 1800–2399")
        if req.latitude is None or req.longitude is None:
            location=geocoder.geocode(req.place,timeout=8)
            if not location:raise ValueError("Doğum yeri bulunamadı; koordinat girin")
            lat,lon=location.latitude,location.longitude
            address=location.address
        else:lat,lon,address=req.latitude,req.longitude,req.place
        tzname=req.timezone or tzfinder.timezone_at(lat=lat,lng=lon)
        if not tzname:raise ValueError("Saat dilimi bulunamadı")
        utc=local.replace(tzinfo=ZoneInfo(tzname)).astimezone(timezone.utc)
        jd=swe.julday(utc.year,utc.month,utc.day,utc.hour+utc.minute/60+utc.second/3600)
        result={}
        for name,body in BODIES.items():
            # Moshier fallback: bundled computation, no external ephemeris files required.
            coords,flags=swe.calc_ut(jd,body,swe.FLG_MOSEPH|swe.FLG_SPEED)
            lonp=coords[0]%360
            result[name]={"longitude":round(lonp,6),"sign":SIGNS[int(lonp//30)],"degree":round(lonp%30,4),"retrograde":coords[3]<0}
        houses=None
        if req.time:
            cusps,ascmc=swe.houses(jd,lat,lon,b"P")
            houses={"cusps":[round(x,6) for x in cusps],"asc":round(ascmc[0],6),"mc":round(ascmc[1],6),"system":"Placidus"}
        aspects=[]
        names=list(result)
        for i,a in enumerate(names):
            for b in names[i+1:]:
                diff=abs(result[a]["longitude"]-result[b]["longitude"]);diff=min(diff,360-diff)
                for angle,label,orb in [(0,"Kavuşum",8),(60,"Sekstil",5),(90,"Kare",6),(120,"Üçgen",6),(180,"Karşıt",8)]:
                    if abs(diff-angle)<=orb:
                        aspects.append({"a":a,"b":b,"type":label,"orb":round(abs(diff-angle),2)})
                        break
        return {"name":req.name,"date":req.date,"time":req.time,"place":address,"latitude":lat,"longitude":lon,"timezone":tzname,"utc":utc.isoformat(),"engine":"Swiss Ephemeris / Moshier","positions":result,"houses":houses,"aspects":aspects,"time_unknown":not bool(req.time),"disclaimer":"Astrolojik yorumlar bilimsel olarak doğrulanmış öngörüler değildir."}
    except Exception as e:
        raise HTTPException(status_code=422,detail=str(e))
