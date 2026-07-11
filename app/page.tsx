"use client";
import { useEffect, useState } from "react";

type Settings = { notionToken:string; intervalsKey:string; databaseId:string };
const key = "workoutsync.credentials.v1";
const defaults: Settings = { notionToken:"", intervalsKey:"", databaseId:"3879cd904ec380a6bb8dd05772b2a25f" };

export default function Home(){
 const [settings,setSettings]=useState(defaults);
 const [sport,setSport]=useState("Course");
 const [details,setDetails]=useState("## Échauffement\n- 10' facile\n\n## Corps de séance\n- 3 x 10' à 4'05-4'10/km récupération 3' facile\n\n## Retour au calme\n- 10' facile");
 const [result,setResult]=useState<any>(null); const [message,setMessage]=useState("Prêt");
 useEffect(()=>{const saved=localStorage.getItem(key); if(saved) setSettings({...defaults,...JSON.parse(saved)});},[]);
 const update=(name:keyof Settings,value:string)=>setSettings(s=>({...s,[name]:value}));
 const save=()=>{localStorage.setItem(key,JSON.stringify(settings));setMessage("Identifiants mémorisés sur cet appareil");};
 async function compile(){setMessage("Compilation…"); const r=await fetch("/api/compile",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sport,details})}); const j=await r.json(); setResult(j); setMessage(r.ok?"Compilation terminée":j.error||"Erreur");}
 return <main><header><p>WORKOUT SYNC</p><h1>Notion → Intervals.icu → Garmin</h1></header><section className="credentials"><input type="password" placeholder="Token Notion" value={settings.notionToken} onChange={e=>update("notionToken",e.target.value)}/><input type="password" placeholder="Clé Intervals" value={settings.intervalsKey} onChange={e=>update("intervalsKey",e.target.value)}/><input value={settings.databaseId} onChange={e=>update("databaseId",e.target.value)}/><button onClick={save}>Mémoriser</button></section><section className="grid"><article><h2>Source</h2><select value={sport} onChange={e=>setSport(e.target.value)}><option>Course</option><option>Vélo</option><option>Home trainer</option></select><textarea value={details} onChange={e=>setDetails(e.target.value)}/><button className="primary" onClick={compile}>Compiler</button></article><article><h2>Script Intervals</h2><pre>{result?.script||"Le résultat apparaîtra ici."}</pre><h3>Validation</h3><div>{result?.records?.map((x:any,i:number)=><p key={i} className={x.status}><b>{x.status}</b> — {x.source}<br/><span>{x.output}</span></p>)}</div></article><article><h2>Payload</h2><pre>{result?JSON.stringify(result,null,2):"Aucun payload."}</pre></article></section><footer>{message}</footer></main>;
}
