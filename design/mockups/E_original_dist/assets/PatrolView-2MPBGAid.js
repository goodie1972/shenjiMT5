import{J as w,M as $,O as C,b as M,b_ as F,cg as T,cd as A,ch as I,bi as D,bR as W,ca as q,j as J,a as Q,h as Y,A as L,p as E,k as G}from"./index-AEW2pwWu.js";import{q as S,u as s,e as H,j as O,g as B,L as i,o as g,a3 as n,Y as l,h as p,i as K,n as z,W as m,F as U,Q as X}from"./vendor-vue-DbQYUZY4.js";import{N as Z,a as ee,b as te}from"./Thing-BqDtyATg.js";import{N as ne}from"./Empty-sfm-qzjU.js";import"./vendor-i18n-404dD7OQ.js";const ae=S({name:"ArrowBack",render(){return s("svg",{xmlns:"http://www.w3.org/2000/svg",viewBox:"0 0 24 24"},s("path",{d:"M0 0h24v24H0V0z",fill:"none"}),s("path",{d:"M19 11H7.83l4.88-4.88c.39-.39.39-1.03 0-1.42-.39-.39-1.02-.39-1.41 0l-6.59 6.59c-.39.39-.39 1.02 0 1.41l6.59 6.59c.39.39 1.02.39 1.41 0 .39-.39.39-1.02 0-1.41L7.83 13H19c.55 0 1-.45 1-1s-.45-1-1-1z"}))}}),le=w([$("page-header-header",`
 margin-bottom: 20px;
 `),$("page-header",`
 display: flex;
 align-items: center;
 justify-content: space-between;
 line-height: 1.5;
 font-size: var(--n-font-size);
 `,[C("main",`
 display: flex;
 flex-wrap: nowrap;
 align-items: center;
 `),C("back",`
 display: flex;
 margin-right: 16px;
 font-size: var(--n-back-size);
 cursor: pointer;
 color: var(--n-back-color);
 transition: color .3s var(--n-bezier);
 `,[w("&:hover","color: var(--n-back-color-hover);"),w("&:active","color: var(--n-back-color-pressed);")]),C("avatar",`
 display: flex;
 margin-right: 12px
 `),C("title",`
 margin-right: 16px;
 transition: color .3s var(--n-bezier);
 font-size: var(--n-title-font-size);
 font-weight: var(--n-title-font-weight);
 color: var(--n-title-text-color);
 `),C("subtitle",`
 font-size: 14px;
 transition: color .3s var(--n-bezier);
 color: var(--n-subtitle-text-color);
 `)]),$("page-header-content",`
 font-size: var(--n-font-size);
 `,[w("&:not(:first-child)","margin-top: 20px;")]),$("page-header-footer",`
 font-size: var(--n-font-size);
 `,[w("&:not(:first-child)","margin-top: 20px;")])]),re=Object.assign(Object.assign({},T.props),{title:String,subtitle:String,extra:String,onBack:Function}),oe=S({name:"PageHeader",props:re,slots:Object,setup(r){const{mergedClsPrefixRef:t,mergedRtlRef:d,inlineThemeDisabled:a}=F(r),u=T("PageHeader","-page-header",le,D,r,t),e=A("PageHeader",d,t),h=H(()=>{const{self:{titleTextColor:f,subtitleTextColor:_,backColor:b,fontSize:k,titleFontSize:y,backSize:v,titleFontWeight:x,backColorHover:o,backColorPressed:P},common:{cubicBezierEaseInOut:R}}=u.value;return{"--n-title-text-color":f,"--n-title-font-size":y,"--n-title-font-weight":x,"--n-font-size":k,"--n-back-size":v,"--n-subtitle-text-color":_,"--n-back-color":b,"--n-back-color-hover":o,"--n-back-color-pressed":P,"--n-bezier":R}}),c=a?I("page-header",void 0,h,r):void 0;return{rtlEnabled:e,mergedClsPrefix:t,cssVars:a?void 0:h,themeClass:c==null?void 0:c.themeClass,onRender:c==null?void 0:c.onRender}},render(){var r;const{onBack:t,title:d,subtitle:a,extra:u,mergedClsPrefix:e,cssVars:h,$slots:c}=this;(r=this.onRender)===null||r===void 0||r.call(this);const{title:f,subtitle:_,extra:b,default:k,header:y,avatar:v,footer:x,back:o}=c,P=t,R=d||f,V=a||_,j=u||b;return s("div",{style:h,class:[`${e}-page-header-wrapper`,this.themeClass,this.rtlEnabled&&`${e}-page-header-wrapper--rtl`]},y?s("div",{class:`${e}-page-header-header`,key:"breadcrumb"},y()):null,(P||v||R||V||j)&&s("div",{class:`${e}-page-header`,key:"header"},s("div",{class:`${e}-page-header__main`,key:"back"},P?s("div",{class:`${e}-page-header__back`,onClick:t},o?o():s(M,{clsPrefix:e},{default:()=>s(ae,null)})):null,v?s("div",{class:`${e}-page-header__avatar`},v()):null,R?s("div",{class:`${e}-page-header__title`,key:"title"},d||f()):null,V?s("div",{class:`${e}-page-header__subtitle`,key:"subtitle"},a||_()):null),j?s("div",{class:`${e}-page-header__extra`},u||b()):null),k?s("div",{class:`${e}-page-header-content`,key:"content"},k()):null,x?s("div",{class:`${e}-page-header-footer`,key:"footer"},x()):null)}}),se=$("p",`
 box-sizing: border-box;
 transition: color .3s var(--n-bezier);
 margin: var(--n-margin);
 font-size: var(--n-font-size);
 line-height: var(--n-line-height);
 color: var(--n-text-color);
`,[w("&:first-child","margin-top: 0;"),w("&:last-child","margin-bottom: 0;")]),ie=Object.assign(Object.assign({},T.props),{depth:[String,Number]}),ce=S({name:"P",props:ie,setup(r){const{mergedClsPrefixRef:t,inlineThemeDisabled:d}=F(r),a=T("Typography","-p",se,W,r,t),u=H(()=>{const{depth:h}=r,c=h||"1",{common:{cubicBezierEaseInOut:f},self:{pFontSize:_,pLineHeight:b,pMargin:k,pTextColor:y,[`pTextColor${c}Depth`]:v}}=a.value;return{"--n-bezier":f,"--n-font-size":_,"--n-line-height":b,"--n-margin":k,"--n-text-color":h===void 0?y:v}}),e=d?I("p",H(()=>`${r.depth||""}`),u,r):void 0;return{mergedClsPrefix:t,cssVars:d?void 0:u,themeClass:e==null?void 0:e.themeClass,onRender:e==null?void 0:e.onRender}},render(){var r;return(r=this.onRender)===null||r===void 0||r.call(this),s("p",{class:[`${this.mergedClsPrefix}-p`,this.themeClass],style:this.cssVars},this.$slots)}}),de={xmlns:"http://www.w3.org/2000/svg","xmlns:xlink":"http://www.w3.org/1999/xlink",viewBox:"0 0 512 512"},N=S({name:"ShieldCheckmarkOutline",render:function(t,d){return i(),O("svg",de,d[0]||(d[0]=[B("path",{fill:"none",stroke:"currentColor","stroke-linecap":"round","stroke-linejoin":"round","stroke-width":"32",d:"M336 176L225.2 304L176 255.8"},null,-1),B("path",{d:"M463.1 112.37C373.68 96.33 336.71 84.45 256 48c-80.71 36.45-117.68 48.33-207.1 64.37C32.7 369.13 240.58 457.79 256 464c15.42-6.21 223.3-94.87 207.1-351.63z",fill:"none",stroke:"currentColor","stroke-linecap":"round","stroke-linejoin":"round","stroke-width":"32"},null,-1)]))}}),fe=S({__name:"PatrolView",setup(r){const t=q(),d={info:"#22c55e",warning:"#eab308",critical:"#ef4444"};return(a,u)=>{const e=Y,h=G,c=J,f=Q,_=oe,b=ce,k=ne,y=te,v=ee,x=Z;return i(),O("div",null,[g(_,{subtitle:a.$t("patrol.subtitle")},{title:n(()=>[g(c,{align:"center",size:"small"},{default:n(()=>[g(e,{color:d[l(t).health],size:"28"},{default:n(()=>[l(t).health==="critical"?(i(),p(l(L),{key:0})):l(t).health==="warning"?(i(),p(l(E),{key:1})):(i(),p(l(N),{key:2}))]),_:1},8,["color"]),B("span",null,m(a.$t("patrol.status")),1),l(t).health==="normal"?(i(),p(h,{key:0,type:"success",size:"small",bordered:!1},{default:n(()=>[z(m(a.$t("patrol.all_ok")),1)]),_:1})):l(t).health==="warning"?(i(),p(h,{key:1,type:"warning",size:"small",bordered:!1},{default:n(()=>[z(m(a.$t("patrol.warning_count",{count:l(t).warningCount})),1)]),_:1})):(i(),p(h,{key:2,type:"error",size:"small",bordered:!1},{default:n(()=>[z(m(a.$t("patrol.critical_count",{count:l(t).criticalCount})),1)]),_:1}))]),_:1})]),extra:n(()=>[g(c,null,{default:n(()=>[g(f,{size:"small",onClick:u[0]||(u[0]=o=>l(t).runPatrol())},{default:n(()=>[z(m(a.$t("patrol.run_now")),1)]),_:1}),g(f,{size:"small",onClick:u[1]||(u[1]=o=>l(t).clearAlerts())},{default:n(()=>[z(m(a.$t("patrol.clear_alerts")),1)]),_:1})]),_:1})]),_:1},8,["subtitle"]),l(t).lastCheckTime?(i(),p(b,{key:0,depth:"3",style:{"font-size":"12px"}},{default:n(()=>[z(m(a.$t("patrol.last_check"))+": "+m(l(t).lastCheckTime),1)]),_:1})):K("",!0),l(t).alerts.length===0?(i(),p(k,{key:1,description:a.$t("patrol.empty"),style:{"margin-top":"40px"}},{icon:n(()=>[g(e,{color:"#22c55e",size:"48"},{default:n(()=>[g(l(N))]),_:1})]),_:1},8,["description"])):(i(),p(x,{key:2,style:{"margin-top":"16px"}},{default:n(()=>[(i(!0),O(U,null,X(l(t).alerts,o=>(i(),p(v,{key:o.id},{default:n(()=>[g(y,null,{avatar:n(()=>[g(e,{color:d[o.level],size:"20"},{default:n(()=>[o.level==="critical"?(i(),p(l(L),{key:0})):o.level==="warning"?(i(),p(l(E),{key:1})):(i(),p(l(N),{key:2}))]),_:2},1032,["color"])]),header:n(()=>[g(c,{align:"center",size:"small"},{default:n(()=>[g(h,{type:o.level==="critical"?"error":o.level==="warning"?"warning":"success",size:"tiny",bordered:!1},{default:n(()=>[z(m(o.level==="critical"?a.$t("patrol.level_critical"):o.level==="warning"?a.$t("patrol.level_warning"):a.$t("patrol.level_info")),1)]),_:2},1032,["type"]),B("span",null,m(o.time),1)]),_:2},1024)]),default:n(()=>[z(" "+m(o.message),1)]),_:2},1024)]),_:2},1024))),128))]),_:1}))])}}});export{fe as default};
