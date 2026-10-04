import{b1 as N,J as w,M as F,bs as H,b_ as T,cg as B,bJ as A,a4 as O,bp as z,aQ as V}from"./index-AEW2pwWu.js";import{q as j,u as P,z as D,F as E,e as x,r as J,P as m}from"./vendor-vue-DbQYUZY4.js";let C=!1;function K(){if(N&&window.CSS&&!C&&(C=!0,"registerProperty"in(window==null?void 0:window.CSS)))try{CSS.registerProperty({name:"--n-color-start",syntax:"<color>",inherits:!1,initialValue:"#0000"}),CSS.registerProperty({name:"--n-color-end",syntax:"<color>",inherits:!1,initialValue:"#0000"})}catch{}}const q=w([F("skeleton",`
 height: 1em;
 width: 100%;
 transition:
 --n-color-start .3s var(--n-bezier),
 --n-color-end .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 animation: 2s skeleton-loading infinite cubic-bezier(0.36, 0, 0.64, 1);
 background-color: var(--n-color-start);
 `),w("@keyframes skeleton-loading",`
 0% {
 background: var(--n-color-start);
 }
 40% {
 background: var(--n-color-end);
 }
 80% {
 background: var(--n-color-start);
 }
 100% {
 background: var(--n-color-start);
 }
 `)]),I=Object.assign(Object.assign({},B.props),{text:Boolean,round:Boolean,circle:Boolean,height:[String,Number],width:[String,Number],size:String,repeat:{type:Number,default:1},animated:{type:Boolean,default:!0},sharp:{type:Boolean,default:!0}}),Q=j({name:"Skeleton",inheritAttrs:!1,props:I,setup(e){K();const{mergedClsPrefixRef:r,mergedComponentPropsRef:n}=T(e),s=x(()=>{var t,o;return e.size||((o=(t=n==null?void 0:n.value)===null||t===void 0?void 0:t.Skeleton)===null||o===void 0?void 0:o.size)}),i=B("Skeleton","-skeleton",q,A,e,r);return{mergedClsPrefix:r,style:x(()=>{var t,o;const u=i.value,{common:{cubicBezierEaseInOut:d}}=u,c=u.self,{color:f,colorEnd:g,borderRadius:a}=c;let v;const{circle:h,sharp:R,round:_,width:l,height:b,text:k,animated:$}=e,S=s.value;S!==void 0&&(v=c[O("height",S)]);const p=h?(t=l??b)!==null&&t!==void 0?t:v:l,y=(o=h?l??b:b)!==null&&o!==void 0?o:v;return{display:k?"inline-block":"",verticalAlign:k?"-0.125em":"",borderRadius:h?"50%":_?"4096px":R?"":a,width:typeof p=="number"?z(p):p,height:typeof y=="number"?z(y):y,animation:$?"":"none","--n-bezier":d,"--n-color-start":f,"--n-color-end":g}})}},render(){const{repeat:e,style:r,mergedClsPrefix:n,$attrs:s}=this,i=P("div",D({class:`${n}-skeleton`,style:r},s));return e>1?P(E,null,H(e,null).map(t=>[i,`
`])):i}}),W=J("trades",()=>{const e=m([]),r=m(!1),n=m(null),s=m(0);let i=0,t="";async function o(d=100,c=0,f){const g=`${d}|${c}|${f||""}`;if(!(g===t&&Date.now()-i<3e4)){t=g,i=Date.now(),r.value=!0,n.value=null;try{const a=await V(d,c,f);e.value=a.trades,s.value=a.total}catch(a){n.value=(a==null?void 0:a.message)||"获取历史成交失败"}finally{r.value=!1}}}function u(){e.value=[],r.value=!1,n.value=null,s.value=0}return{items:e,loading:r,error:n,total:s,fetch:o,$reset:u}});export{Q as N,W as u};
