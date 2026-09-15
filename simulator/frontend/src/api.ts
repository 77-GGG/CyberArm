export let session='';
export const client=crypto.randomUUID();
export function setSession(value:string){session=value;}
export async function api(path:string,body?:unknown){
 const response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Session':session,'X-Client':client},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json();
 if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
 return data;
}
