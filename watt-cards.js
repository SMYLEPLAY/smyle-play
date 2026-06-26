/* ─────────────────────────────────────────────────────────────────────────
   WATT — cartes sons en « éclats de verre wireframe ».
   Additif : pour chaque .mp-son-card on pose une forme irrégulière (clip-path)
   et on dessine un maillage triangulé lumineux sur un <canvas> superposé
   (pointer-events:none → n'intercepte aucun clic). Le contenu et les mécaniques
   ne sont pas modifiés. Re-rendu auto quand la grille change (MutationObserver).
   Réf : OBSIDIAN/02_WATT/2026-06-25_WATT_CREATIVE_DIRECTION.md
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  // Formes d'éclats (en %), assez ouvertes au centre pour laisser le contenu.
  var POLYS = [
    [[6,3],[70,0],[97,15],[100,72],[82,100],[18,97],[0,58],[3,20]],
    [[3,10],[44,0],[92,5],[100,50],[90,93],[46,100],[7,82],[0,40]],
    [[11,0],[72,4],[100,28],[95,82],[60,100],[9,91],[2,46]],
    [[0,16],[38,2],[85,0],[100,40],[87,88],[40,100],[6,70]],
    [[5,5],[58,0],[100,22],[96,66],[80,100],[24,95],[0,48]]
  ];
  function rng(s){return function(){s|=0;s=s+0x6D2B79F5|0;var t=Math.imul(s^s>>>15,1|s);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
  function inPoly(x,y,P){var c=false;for(var i=0,j=P.length-1;i<P.length;j=i++){var xi=P[i][0],yi=P[i][1],xj=P[j][0],yj=P[j][1];if(((yi>y)!=(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi)+xi))c=!c;}return c;}

  function draw(card, idx){
    try{
      var W=card.clientWidth, H=card.clientHeight;
      if(!W||!H) return;
      var polyPct=POLYS[idx%POLYS.length];
      card.style.clipPath='polygon('+polyPct.map(function(p){return p[0]+'% '+p[1]+'%';}).join(',')+')';
      var poly=polyPct.map(function(p){return [p[0]/100*W,p[1]/100*H];});

      var cv=card.querySelector('canvas.wf');
      if(!cv){cv=document.createElement('canvas');cv.className='wf';cv.setAttribute('aria-hidden','true');card.appendChild(cv);}
      var dpr=Math.min(window.devicePixelRatio||1,2);
      cv.width=W*dpr;cv.height=H*dpr;cv.style.width=W+'px';cv.style.height=H+'px';
      var x=cv.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,W,H);

      var r=rng(idx*131+9), pts=poly.slice();
      for(var e=0;e<poly.length;e++){var a=poly[e],b=poly[(e+1)%poly.length];for(var k=1;k<4;k++)pts.push([a[0]+(b[0]-a[0])*k/4,a[1]+(b[1]-a[1])*k/4]);}
      var guard=0;while(pts.length<46&&guard<600){guard++;var px=r()*W,py=r()*H;if(inPoly(px,py,poly))pts.push([px,py]);}

      // arêtes : chaque point relié à ses 3 plus proches (maillage)
      var seen={},edges=[];
      for(var i=0;i<pts.length;i++){var d=[];for(var j=0;j<pts.length;j++){if(i===j)continue;var dx=pts[i][0]-pts[j][0],dy=pts[i][1]-pts[j][1];d.push([dx*dx+dy*dy,j]);}d.sort(function(m,n){return m[0]-n[0];});for(var t=0;t<3&&t<d.length;t++){var jj=d[t][1];var key=i<jj?i+'_'+jj:jj+'_'+i;if(seen[key])continue;seen[key]=1;edges.push([i,jj]);}}

      x.save();
      x.beginPath();x.moveTo(poly[0][0],poly[0][1]);poly.forEach(function(p){x.lineTo(p[0],p[1]);});x.closePath();x.clip();
      function strokeEdges(w,blur,glow,col){x.lineWidth=w;x.shadowBlur=blur;x.shadowColor=glow;x.strokeStyle=col;x.beginPath();edges.forEach(function(ed){x.moveTo(pts[ed[0]][0],pts[ed[0]][1]);x.lineTo(pts[ed[1]][0],pts[ed[1]][1]);});x.stroke();}
      strokeEdges(1.3,7,'rgba(120,160,255,.16)','rgba(120,160,255,.5)');
      strokeEdges(.5,0,'transparent','rgba(205,222,255,.5)');
      x.fillStyle='rgba(220,235,255,.65)';x.shadowBlur=5;x.shadowColor='rgba(150,190,255,.7)';
      pts.forEach(function(p){if(r()>.74){x.beginPath();x.arc(p[0],p[1],1+r()*1.1,0,7);x.fill();}});
      x.restore();

      // silhouette lumineuse
      x.save();x.lineJoin='round';x.shadowBlur=9;x.shadowColor='rgba(150,190,255,.8)';x.strokeStyle='rgba(222,238,255,.85)';x.lineWidth=1.3;
      x.beginPath();x.moveTo(poly[0][0],poly[0][1]);poly.forEach(function(p){x.lineTo(p[0],p[1]);});x.closePath();x.stroke();x.restore();
    }catch(e){/* effet optionnel */}
  }

  function renderAll(){
    var cards=document.querySelectorAll('.mp-son-card');
    cards.forEach(function(c,i){draw(c,i);});
  }
  var _t;
  function schedule(){clearTimeout(_t);_t=setTimeout(renderAll,120);}

  function init(){
    renderAll();
    window.addEventListener('resize',schedule,{passive:true});
    try{
      var mo=new MutationObserver(function(muts){
        for(var i=0;i<muts.length;i++){if(muts[i].addedNodes&&muts[i].addedNodes.length){schedule();return;}}
      });
      mo.observe(document.body,{childList:true,subtree:true});
    }catch(e){}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);
  else init();
})();
