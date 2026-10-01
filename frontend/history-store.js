(() => {
  const DB_NAME = 'researchops-vercel-history';
  const DB_VERSION = 1;
  const STORE = 'jobs';

  function openDb(){
    return new Promise((resolve,reject)=>{
      const req=indexedDB.open(DB_NAME,DB_VERSION);
      req.onupgradeneeded=()=>{
        const db=req.result;
        if(!db.objectStoreNames.contains(STORE)){
          const st=db.createObjectStore(STORE,{keyPath:'research_id'});
          st.createIndex('created_at','created_at',{unique:false});
          st.createIndex('status','status',{unique:false});
        }
      };
      req.onsuccess=()=>resolve(req.result);
      req.onerror=()=>reject(req.error || new Error('Could not open browser history database'));
    });
  }

  async function tx(mode, fn){
    const db=await openDb();
    try{
      return await new Promise((resolve,reject)=>{
        const t=db.transaction(STORE,mode), st=t.objectStore(STORE);
        let out;
        try{ out=fn(st); }catch(e){ reject(e); return; }
        t.oncomplete=()=>resolve(out);
        t.onerror=()=>reject(t.error || new Error('History transaction failed'));
        t.onabort=()=>reject(t.error || new Error('History transaction aborted'));
      });
    }finally{ db.close(); }
  }

  async function put(job){
    return tx('readwrite', st=>st.put(job));
  }

  async function get(id){
    const db=await openDb();
    try{
      return await new Promise((resolve,reject)=>{
        const r=db.transaction(STORE,'readonly').objectStore(STORE).get(id);
        r.onsuccess=()=>resolve(r.result || null);
        r.onerror=()=>reject(r.error);
      });
    }finally{ db.close(); }
  }

  async function remove(id){
    return tx('readwrite', st=>st.delete(id));
  }

  async function list(status='all'){
    const db=await openDb();
    try{
      return await new Promise((resolve,reject)=>{
        const r=db.transaction(STORE,'readonly').objectStore(STORE).getAll();
        r.onsuccess=()=>{
          let rows=r.result || [];
          if(status && status!=='all') rows=rows.filter(x=>x.status===status);
          rows.sort((a,b)=>String(b.created_at||'').localeCompare(String(a.created_at||'')));
          resolve(rows);
        };
        r.onerror=()=>reject(r.error);
      });
    }finally{ db.close(); }
  }

  window.ResearchHistory={put,get,remove,list};
})();
