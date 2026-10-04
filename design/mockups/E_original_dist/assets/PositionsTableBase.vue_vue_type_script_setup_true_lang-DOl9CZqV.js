import{q as U,a4 as G,u as t,b as ce,z as Fe,a0 as ee,P as B,v as de,a2 as Ee,a1 as Me,H as Te,e as R,M as V,X as te,L as j,j as He,Y as _,h as W,a3 as P,o as H,n as oe,W as re}from"./vendor-vue-DbQYUZY4.js";import{F as Oe,S as ue,b_ as Q,cd as Pe,c4 as De,ae as Z,U as Ne,ad as Ie,bm as Le,bb as je,J as d,$ as Y,M as y,P as O,O as M,am as Ue,cj as We,L as Ae,b3 as Ve,cg as X,af as Ye,c8 as ie,c2 as Xe,ch as fe,ai as Ke,R as L,as as ne,N as qe,bP as Je,b as Ge,bC as Qe,E as Ze,W as et,l as tt,I as ot,a4 as A,cb as rt,c9 as it,b$ as nt,k as K,j as q,a as J,_ as st,v as at,bc as lt}from"./index-AEW2pwWu.js";import{g as ct,t as dt}from"./strategyColors-CGpQSzIu.js";import{u as ut}from"./vendor-i18n-404dD7OQ.js";import{f as se}from"./timeFormat-BhCwhx__.js";import{N as ae}from"./DataTable-bRiSS7_N.js";import{N as ft}from"./Select-DIJ0fyT7.js";import{_ as le}from"./FormItem-C-v3Hrgd.js";import{N as ht}from"./Empty-sfm-qzjU.js";const mt=U({name:"NDrawerContent",inheritAttrs:!1,props:{blockScroll:Boolean,show:{type:Boolean,default:void 0},displayDirective:{type:String,required:!0},placement:{type:String,required:!0},contentClass:String,contentStyle:[Object,String],nativeScrollbar:{type:Boolean,required:!0},scrollbarProps:Object,trapFocus:{type:Boolean,default:!0},autoFocus:{type:Boolean,default:!0},showMask:{type:[Boolean,String],required:!0},maxWidth:Number,maxHeight:Number,minWidth:Number,minHeight:Number,resizable:Boolean,onClickoutside:Function,onAfterLeave:Function,onAfterEnter:Function,onEsc:Function},setup(r){const e=B(!!r.show),i=B(null),l=de(Z);let v=0,b="",p=null;const f=B(!1),u=B(!1),h=R(()=>r.placement==="top"||r.placement==="bottom"),{mergedClsPrefixRef:z,mergedRtlRef:E}=Q(r),T=Pe("Drawer",E,z),$=s,x=c=>{u.value=!0,v=h.value?c.clientY:c.clientX,b=document.body.style.cursor,document.body.style.cursor=h.value?"ns-resize":"ew-resize",document.body.addEventListener("mousemove",S),document.body.addEventListener("mouseleave",$),document.body.addEventListener("mouseup",s)},o=()=>{p!==null&&(window.clearTimeout(p),p=null),u.value?f.value=!0:p=window.setTimeout(()=>{f.value=!0},300)},n=()=>{p!==null&&(window.clearTimeout(p),p=null),f.value=!1},{doUpdateHeight:g,doUpdateWidth:a}=l,D=c=>{const{maxWidth:w}=r;if(w&&c>w)return w;const{minWidth:k}=r;return k&&c<k?k:c},N=c=>{const{maxHeight:w}=r;if(w&&c>w)return w;const{minHeight:k}=r;return k&&c<k?k:c};function S(c){var w,k;if(u.value)if(h.value){let F=((w=i.value)===null||w===void 0?void 0:w.offsetHeight)||0;const I=v-c.clientY;F+=r.placement==="bottom"?I:-I,F=N(F),g(F),v=c.clientY}else{let F=((k=i.value)===null||k===void 0?void 0:k.offsetWidth)||0;const I=v-c.clientX;F+=r.placement==="right"?I:-I,F=D(F),a(F),v=c.clientX}}function s(){u.value&&(v=0,u.value=!1,document.body.style.cursor=b,document.body.removeEventListener("mousemove",S),document.body.removeEventListener("mouseup",s),document.body.removeEventListener("mouseleave",$))}Ee(()=>{r.show&&(e.value=!0)}),Me(()=>r.show,c=>{c||s()}),Te(()=>{s()});const m=R(()=>{const{show:c}=r,w=[[ee,c]];return r.showMask||w.push([Ne,r.onClickoutside,void 0,{capture:!0}]),w});function C(){var c;e.value=!1,(c=r.onAfterLeave)===null||c===void 0||c.call(r)}return De(R(()=>r.blockScroll&&e.value)),V(Ie,i),V(Le,null),V(je,null),{bodyRef:i,rtlEnabled:T,mergedClsPrefix:l.mergedClsPrefixRef,isMounted:l.isMountedRef,mergedTheme:l.mergedThemeRef,displayed:e,transitionName:R(()=>({right:"slide-in-from-right-transition",left:"slide-in-from-left-transition",top:"slide-in-from-top-transition",bottom:"slide-in-from-bottom-transition"})[r.placement]),handleAfterLeave:C,bodyDirectives:m,handleMousedownResizeTrigger:x,handleMouseenterResizeTrigger:o,handleMouseleaveResizeTrigger:n,isDragging:u,isHoverOnResizeTrigger:f}},render(){const{$slots:r,mergedClsPrefix:e}=this;return this.displayDirective==="show"||this.displayed||this.show?G(t("div",{role:"none"},t(Oe,{disabled:!this.showMask||!this.trapFocus,active:this.show,autoFocus:this.autoFocus,onEsc:this.onEsc},{default:()=>t(ce,{name:this.transitionName,appear:this.isMounted,onAfterEnter:this.onAfterEnter,onAfterLeave:this.handleAfterLeave},{default:()=>G(t("div",Fe(this.$attrs,{role:"dialog",ref:"bodyRef","aria-modal":"true",class:[`${e}-drawer`,this.rtlEnabled&&`${e}-drawer--rtl`,`${e}-drawer--${this.placement}-placement`,this.isDragging&&`${e}-drawer--unselectable`,this.nativeScrollbar&&`${e}-drawer--native-scrollbar`]}),[this.resizable?t("div",{class:[`${e}-drawer__resize-trigger`,(this.isDragging||this.isHoverOnResizeTrigger)&&`${e}-drawer__resize-trigger--hover`],onMouseenter:this.handleMouseenterResizeTrigger,onMouseleave:this.handleMouseleaveResizeTrigger,onMousedown:this.handleMousedownResizeTrigger}):null,this.nativeScrollbar?t("div",{class:[`${e}-drawer-content-wrapper`,this.contentClass],style:this.contentStyle,role:"none"},r):t(ue,Object.assign({},this.scrollbarProps,{contentStyle:this.contentStyle,contentClass:[`${e}-drawer-content-wrapper`,this.contentClass],theme:this.mergedTheme.peers.Scrollbar,themeOverrides:this.mergedTheme.peerOverrides.Scrollbar}),r)]),this.bodyDirectives)})})),[[ee,this.displayDirective==="if"||this.displayed||this.show]]):null}}),{cubicBezierEaseIn:pt,cubicBezierEaseOut:gt}=Y;function vt({duration:r="0.3s",leaveDuration:e="0.2s",name:i="slide-in-from-bottom"}={}){return[d(`&.${i}-transition-leave-active`,{transition:`transform ${e} ${pt}`}),d(`&.${i}-transition-enter-active`,{transition:`transform ${r} ${gt}`}),d(`&.${i}-transition-enter-to`,{transform:"translateY(0)"}),d(`&.${i}-transition-enter-from`,{transform:"translateY(100%)"}),d(`&.${i}-transition-leave-from`,{transform:"translateY(0)"}),d(`&.${i}-transition-leave-to`,{transform:"translateY(100%)"})]}const{cubicBezierEaseIn:bt,cubicBezierEaseOut:yt}=Y;function wt({duration:r="0.3s",leaveDuration:e="0.2s",name:i="slide-in-from-left"}={}){return[d(`&.${i}-transition-leave-active`,{transition:`transform ${e} ${bt}`}),d(`&.${i}-transition-enter-active`,{transition:`transform ${r} ${yt}`}),d(`&.${i}-transition-enter-to`,{transform:"translateX(0)"}),d(`&.${i}-transition-enter-from`,{transform:"translateX(-100%)"}),d(`&.${i}-transition-leave-from`,{transform:"translateX(0)"}),d(`&.${i}-transition-leave-to`,{transform:"translateX(-100%)"})]}const{cubicBezierEaseIn:_t,cubicBezierEaseOut:xt}=Y;function zt({duration:r="0.3s",leaveDuration:e="0.2s",name:i="slide-in-from-right"}={}){return[d(`&.${i}-transition-leave-active`,{transition:`transform ${e} ${_t}`}),d(`&.${i}-transition-enter-active`,{transition:`transform ${r} ${xt}`}),d(`&.${i}-transition-enter-to`,{transform:"translateX(0)"}),d(`&.${i}-transition-enter-from`,{transform:"translateX(100%)"}),d(`&.${i}-transition-leave-from`,{transform:"translateX(0)"}),d(`&.${i}-transition-leave-to`,{transform:"translateX(100%)"})]}const{cubicBezierEaseIn:Ct,cubicBezierEaseOut:kt}=Y;function $t({duration:r="0.3s",leaveDuration:e="0.2s",name:i="slide-in-from-top"}={}){return[d(`&.${i}-transition-leave-active`,{transition:`transform ${e} ${Ct}`}),d(`&.${i}-transition-enter-active`,{transition:`transform ${r} ${kt}`}),d(`&.${i}-transition-enter-to`,{transform:"translateY(0)"}),d(`&.${i}-transition-enter-from`,{transform:"translateY(-100%)"}),d(`&.${i}-transition-leave-from`,{transform:"translateY(0)"}),d(`&.${i}-transition-leave-to`,{transform:"translateY(-100%)"})]}const St=d([y("drawer",`
 word-break: break-word;
 line-height: var(--n-line-height);
 position: absolute;
 pointer-events: all;
 box-shadow: var(--n-box-shadow);
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 background-color: var(--n-color);
 color: var(--n-text-color);
 box-sizing: border-box;
 `,[zt(),wt(),$t(),vt(),O("unselectable",`
 user-select: none; 
 -webkit-user-select: none;
 `),O("native-scrollbar",[y("drawer-content-wrapper",`
 overflow: auto;
 height: 100%;
 `)]),M("resize-trigger",`
 position: absolute;
 background-color: #0000;
 transition: background-color .3s var(--n-bezier);
 `,[O("hover",`
 background-color: var(--n-resize-trigger-color-hover);
 `)]),y("drawer-content-wrapper",`
 box-sizing: border-box;
 `),y("drawer-content",`
 height: 100%;
 display: flex;
 flex-direction: column;
 `,[O("native-scrollbar",[y("drawer-body-content-wrapper",`
 height: 100%;
 overflow: auto;
 `)]),y("drawer-body",`
 flex: 1 0 0;
 overflow: hidden;
 `),y("drawer-body-content-wrapper",`
 box-sizing: border-box;
 padding: var(--n-body-padding);
 `),y("drawer-header",`
 font-weight: var(--n-title-font-weight);
 line-height: 1;
 font-size: var(--n-title-font-size);
 color: var(--n-title-text-color);
 padding: var(--n-header-padding);
 transition: border .3s var(--n-bezier);
 border-bottom: 1px solid var(--n-divider-color);
 border-bottom: var(--n-header-border-bottom);
 display: flex;
 justify-content: space-between;
 align-items: center;
 `,[M("main",`
 flex: 1;
 `),M("close",`
 margin-left: 6px;
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 `)]),y("drawer-footer",`
 display: flex;
 justify-content: flex-end;
 border-top: var(--n-footer-border-top);
 transition: border .3s var(--n-bezier);
 padding: var(--n-footer-padding);
 `)]),O("right-placement",`
 top: 0;
 bottom: 0;
 right: 0;
 border-top-left-radius: var(--n-border-radius);
 border-bottom-left-radius: var(--n-border-radius);
 `,[M("resize-trigger",`
 width: 3px;
 height: 100%;
 top: 0;
 left: 0;
 transform: translateX(-1.5px);
 cursor: ew-resize;
 `)]),O("left-placement",`
 top: 0;
 bottom: 0;
 left: 0;
 border-top-right-radius: var(--n-border-radius);
 border-bottom-right-radius: var(--n-border-radius);
 `,[M("resize-trigger",`
 width: 3px;
 height: 100%;
 top: 0;
 right: 0;
 transform: translateX(1.5px);
 cursor: ew-resize;
 `)]),O("top-placement",`
 top: 0;
 left: 0;
 right: 0;
 border-bottom-left-radius: var(--n-border-radius);
 border-bottom-right-radius: var(--n-border-radius);
 `,[M("resize-trigger",`
 width: 100%;
 height: 3px;
 bottom: 0;
 left: 0;
 transform: translateY(1.5px);
 cursor: ns-resize;
 `)]),O("bottom-placement",`
 left: 0;
 bottom: 0;
 right: 0;
 border-top-left-radius: var(--n-border-radius);
 border-top-right-radius: var(--n-border-radius);
 `,[M("resize-trigger",`
 width: 100%;
 height: 3px;
 top: 0;
 left: 0;
 transform: translateY(-1.5px);
 cursor: ns-resize;
 `)])]),d("body",[d(">",[y("drawer-container",`
 position: fixed;
 `)])]),y("drawer-container",`
 position: relative;
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 pointer-events: none;
 `,[d("> *",`
 pointer-events: all;
 `)]),y("drawer-mask",`
 background-color: rgba(0, 0, 0, .3);
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `,[O("invisible",`
 background-color: rgba(0, 0, 0, 0)
 `),Ue({enterDuration:"0.2s",leaveDuration:"0.2s",enterCubicBezier:"var(--n-bezier-in)",leaveCubicBezier:"var(--n-bezier-out)"})])]),Bt=Object.assign(Object.assign({},X.props),{show:Boolean,width:[Number,String],height:[Number,String],placement:{type:String,default:"right"},maskClosable:{type:Boolean,default:!0},showMask:{type:[Boolean,String],default:!0},to:[String,Object],displayDirective:{type:String,default:"if"},nativeScrollbar:{type:Boolean,default:!0},zIndex:Number,onMaskClick:Function,scrollbarProps:Object,contentClass:String,contentStyle:[Object,String],trapFocus:{type:Boolean,default:!0},onEsc:Function,autoFocus:{type:Boolean,default:!0},closeOnEsc:{type:Boolean,default:!0},blockScroll:{type:Boolean,default:!0},maxWidth:Number,maxHeight:Number,minWidth:Number,minHeight:Number,resizable:Boolean,defaultWidth:{type:[Number,String],default:251},defaultHeight:{type:[Number,String],default:251},onUpdateWidth:[Function,Array],onUpdateHeight:[Function,Array],"onUpdate:width":[Function,Array],"onUpdate:height":[Function,Array],"onUpdate:show":[Function,Array],onUpdateShow:[Function,Array],onAfterEnter:Function,onAfterLeave:Function,drawerStyle:[String,Object],drawerClass:String,target:null,onShow:Function,onHide:Function}),Rt=U({name:"Drawer",inheritAttrs:!1,props:Bt,setup(r){const{mergedClsPrefixRef:e,namespaceRef:i,inlineThemeDisabled:l}=Q(r),v=Ve(),b=X("Drawer","-drawer",St,Ye,r,e),p=B(r.defaultWidth),f=B(r.defaultHeight),u=ie(te(r,"width"),p),h=ie(te(r,"height"),f),z=R(()=>{const{placement:s}=r;return s==="top"||s==="bottom"?"":ne(u.value)}),E=R(()=>{const{placement:s}=r;return s==="left"||s==="right"?"":ne(h.value)}),T=s=>{const{onUpdateWidth:m,"onUpdate:width":C}=r;m&&L(m,s),C&&L(C,s),p.value=s},$=s=>{const{onUpdateHeight:m,"onUpdate:width":C}=r;m&&L(m,s),C&&L(C,s),f.value=s},x=R(()=>[{width:z.value,height:E.value},r.drawerStyle||""]);function o(s){const{onMaskClick:m,maskClosable:C}=r;C&&D(!1),m&&m(s)}function n(s){o(s)}const g=Xe();function a(s){var m;(m=r.onEsc)===null||m===void 0||m.call(r),r.show&&r.closeOnEsc&&Ke(s)&&(g.value||D(!1))}function D(s){const{onHide:m,onUpdateShow:C,"onUpdate:show":c}=r;C&&L(C,s),c&&L(c,s),m&&!s&&L(m,s)}V(Z,{isMountedRef:v,mergedThemeRef:b,mergedClsPrefixRef:e,doUpdateShow:D,doUpdateHeight:$,doUpdateWidth:T});const N=R(()=>{const{common:{cubicBezierEaseInOut:s,cubicBezierEaseIn:m,cubicBezierEaseOut:C},self:{color:c,textColor:w,boxShadow:k,lineHeight:F,headerPadding:I,footerPadding:he,borderRadius:me,bodyPadding:pe,titleFontSize:ge,titleTextColor:ve,titleFontWeight:be,headerBorderBottom:ye,footerBorderTop:we,closeIconColor:_e,closeIconColorHover:xe,closeIconColorPressed:ze,closeColorHover:Ce,closeColorPressed:ke,closeIconSize:$e,closeSize:Se,closeBorderRadius:Be,resizableTriggerColorHover:Re}}=b.value;return{"--n-line-height":F,"--n-color":c,"--n-border-radius":me,"--n-text-color":w,"--n-box-shadow":k,"--n-bezier":s,"--n-bezier-out":C,"--n-bezier-in":m,"--n-header-padding":I,"--n-body-padding":pe,"--n-footer-padding":he,"--n-title-text-color":ve,"--n-title-font-size":ge,"--n-title-font-weight":be,"--n-header-border-bottom":ye,"--n-footer-border-top":we,"--n-close-icon-color":_e,"--n-close-icon-color-hover":xe,"--n-close-icon-color-pressed":ze,"--n-close-size":Se,"--n-close-color-hover":Ce,"--n-close-color-pressed":ke,"--n-close-icon-size":$e,"--n-close-border-radius":Be,"--n-resize-trigger-color-hover":Re}}),S=l?fe("drawer",void 0,N,r):void 0;return{mergedClsPrefix:e,namespace:i,mergedBodyStyle:x,handleOutsideClick:n,handleMaskClick:o,handleEsc:a,mergedTheme:b,cssVars:l?void 0:N,themeClass:S==null?void 0:S.themeClass,onRender:S==null?void 0:S.onRender,isMounted:v}},render(){const{mergedClsPrefix:r}=this;return t(Ae,{to:this.to,show:this.show},{default:()=>{var e;return(e=this.onRender)===null||e===void 0||e.call(this),G(t("div",{class:[`${r}-drawer-container`,this.namespace,this.themeClass],style:this.cssVars,role:"none"},this.showMask?t(ce,{name:"fade-in-transition",appear:this.isMounted},{default:()=>this.show?t("div",{"aria-hidden":!0,class:[`${r}-drawer-mask`,this.showMask==="transparent"&&`${r}-drawer-mask--invisible`],onClick:this.handleMaskClick}):null}):null,t(mt,Object.assign({},this.$attrs,{class:[this.drawerClass,this.$attrs.class],style:[this.mergedBodyStyle,this.$attrs.style],blockScroll:this.blockScroll,contentStyle:this.contentStyle,contentClass:this.contentClass,placement:this.placement,scrollbarProps:this.scrollbarProps,show:this.show,displayDirective:this.displayDirective,nativeScrollbar:this.nativeScrollbar,onAfterEnter:this.onAfterEnter,onAfterLeave:this.onAfterLeave,trapFocus:this.trapFocus,autoFocus:this.autoFocus,resizable:this.resizable,maxHeight:this.maxHeight,minHeight:this.minHeight,maxWidth:this.maxWidth,minWidth:this.minWidth,showMask:this.showMask,onEsc:this.handleEsc,onClickoutside:this.handleOutsideClick}),this.$slots)),[[We,{zIndex:this.zIndex,enabled:this.show}]])}})}}),Ft={title:String,headerClass:String,headerStyle:[Object,String],footerClass:String,footerStyle:[Object,String],bodyClass:String,bodyStyle:[Object,String],bodyContentClass:String,bodyContentStyle:[Object,String],nativeScrollbar:{type:Boolean,default:!0},scrollbarProps:Object,closable:Boolean},Et=U({name:"DrawerContent",props:Ft,slots:Object,setup(){const r=de(Z,null);r||Je("drawer-content","`n-drawer-content` must be placed inside `n-drawer`.");const{doUpdateShow:e}=r;function i(){e(!1)}return{handleCloseClick:i,mergedTheme:r.mergedThemeRef,mergedClsPrefix:r.mergedClsPrefixRef}},render(){const{title:r,mergedClsPrefix:e,nativeScrollbar:i,mergedTheme:l,bodyClass:v,bodyStyle:b,bodyContentClass:p,bodyContentStyle:f,headerClass:u,headerStyle:h,footerClass:z,footerStyle:E,scrollbarProps:T,closable:$,$slots:x}=this;return t("div",{role:"none",class:[`${e}-drawer-content`,i&&`${e}-drawer-content--native-scrollbar`]},x.header||r||$?t("div",{class:[`${e}-drawer-header`,u],style:h,role:"none"},t("div",{class:`${e}-drawer-header__main`,role:"heading","aria-level":"1"},x.header!==void 0?x.header():r),$&&t(qe,{onClick:this.handleCloseClick,clsPrefix:e,class:`${e}-drawer-header__close`,absolute:!0})):null,i?t("div",{class:[`${e}-drawer-body`,v],style:b,role:"none"},t("div",{class:[`${e}-drawer-body-content-wrapper`,p],style:f,role:"none"},x)):t(ue,Object.assign({themeOverrides:l.peerOverrides.Scrollbar,theme:l.peers.Scrollbar},T,{class:`${e}-drawer-body`,contentClass:[`${e}-drawer-body-content-wrapper`,p],contentStyle:f}),x),x.footer?t("div",{class:[`${e}-drawer-footer`,z],style:E,role:"none"},x.footer()):null)}});function Mt(){return t("svg",{xmlns:"http://www.w3.org/2000/svg",viewBox:"0 0 36 36"},t("path",{fill:"#EF9645",d:"M15.5 2.965c1.381 0 2.5 1.119 2.5 2.5v.005L20.5.465c1.381 0 2.5 1.119 2.5 2.5V4.25l2.5-1.535c1.381 0 2.5 1.119 2.5 2.5V8.75L29 18H15.458L15.5 2.965z"}),t("path",{fill:"#FFDC5D",d:"M4.625 16.219c1.381-.611 3.354.208 4.75 2.188.917 1.3 1.187 3.151 2.391 3.344.46.073 1.234-.313 1.234-1.397V4.5s0-2 2-2 2 2 2 2v11.633c0-.029 1-.064 1-.082V2s0-2 2-2 2 2 2 2v14.053c0 .017 1 .041 1 .069V4.25s0-2 2-2 2 2 2 2v12.638c0 .118 1 .251 1 .398V8.75s0-2 2-2 2 2 2 2V24c0 6.627-5.373 12-12 12-4.775 0-8.06-2.598-9.896-5.292C8.547 28.423 8.096 26.051 8 25.334c0 0-.123-1.479-1.156-2.865-1.469-1.969-2.5-3.156-3.125-3.866-.317-.359-.625-1.707.906-2.384z"}))}function Tt(){return t("svg",{xmlns:"http://www.w3.org/2000/svg",viewBox:"0 0 36 36"},t("circle",{fill:"#FFCB4C",cx:"18",cy:"17.018",r:"17"}),t("path",{fill:"#65471B",d:"M14.524 21.036c-.145-.116-.258-.274-.312-.464-.134-.46.13-.918.59-1.021 4.528-1.021 7.577 1.363 7.706 1.465.384.306.459.845.173 1.205-.286.358-.828.401-1.211.097-.11-.084-2.523-1.923-6.182-1.098-.274.061-.554-.016-.764-.184z"}),t("ellipse",{fill:"#65471B",cx:"13.119",cy:"11.174",rx:"2.125",ry:"2.656"}),t("ellipse",{fill:"#65471B",cx:"24.375",cy:"12.236",rx:"2.125",ry:"2.656"}),t("path",{fill:"#F19020",d:"M17.276 35.149s1.265-.411 1.429-1.352c.173-.972-.624-1.167-.624-1.167s1.041-.208 1.172-1.376c.123-1.101-.861-1.363-.861-1.363s.97-.4 1.016-1.539c.038-.959-.995-1.428-.995-1.428s5.038-1.221 5.556-1.341c.516-.12 1.32-.615 1.069-1.694-.249-1.08-1.204-1.118-1.697-1.003-.494.115-6.744 1.566-8.9 2.068l-1.439.334c-.54.127-.785-.11-.404-.512.508-.536.833-1.129.946-2.113.119-1.035-.232-2.313-.433-2.809-.374-.921-1.005-1.649-1.734-1.899-1.137-.39-1.945.321-1.542 1.561.604 1.854.208 3.375-.833 4.293-2.449 2.157-3.588 3.695-2.83 6.973.828 3.575 4.377 5.876 7.952 5.048l3.152-.681z"}),t("path",{fill:"#65471B",d:"M9.296 6.351c-.164-.088-.303-.224-.391-.399-.216-.428-.04-.927.393-1.112 4.266-1.831 7.699-.043 7.843.034.433.231.608.747.391 1.154-.216.405-.74.546-1.173.318-.123-.063-2.832-1.432-6.278.047-.257.109-.547.085-.785-.042zm12.135 3.75c-.156-.098-.286-.243-.362-.424-.187-.442.023-.927.468-1.084 4.381-1.536 7.685.48 7.823.567.415.26.555.787.312 1.178-.242.39-.776.495-1.191.238-.12-.072-2.727-1.621-6.267-.379-.266.091-.553.046-.783-.096z"}))}function Ht(){return t("svg",{xmlns:"http://www.w3.org/2000/svg",viewBox:"0 0 36 36"},t("ellipse",{fill:"#292F33",cx:"18",cy:"26",rx:"18",ry:"10"}),t("ellipse",{fill:"#66757F",cx:"18",cy:"24",rx:"18",ry:"10"}),t("path",{fill:"#E1E8ED",d:"M18 31C3.042 31 1 16 1 12h34c0 2-1.958 19-17 19z"}),t("path",{fill:"#77B255",d:"M35 12.056c0 5.216-7.611 9.444-17 9.444S1 17.271 1 12.056C1 6.84 8.611 3.611 18 3.611s17 3.229 17 8.445z"}),t("ellipse",{fill:"#A6D388",cx:"18",cy:"13",rx:"15",ry:"7"}),t("path",{d:"M21 17c-.256 0-.512-.098-.707-.293-2.337-2.337-2.376-4.885-.125-8.262.739-1.109.9-2.246.478-3.377-.461-1.236-1.438-1.996-1.731-2.077-.553 0-.958-.443-.958-.996 0-.552.491-.995 1.043-.995.997 0 2.395 1.153 3.183 2.625 1.034 1.933.91 4.039-.351 5.929-1.961 2.942-1.531 4.332-.125 5.738.391.391.391 1.023 0 1.414-.195.196-.451.294-.707.294zm-6-2c-.256 0-.512-.098-.707-.293-2.337-2.337-2.376-4.885-.125-8.262.727-1.091.893-2.083.494-2.947-.444-.961-1.431-1.469-1.684-1.499-.552 0-.989-.447-.989-1 0-.552.458-1 1.011-1 .997 0 2.585.974 3.36 2.423.481.899 1.052 2.761-.528 5.131-1.961 2.942-1.531 4.332-.125 5.738.391.391.391 1.023 0 1.414-.195.197-.451.295-.707.295z",fill:"#5C913B"}))}function Ot(){return t("svg",{xmlns:"http://www.w3.org/2000/svg",viewBox:"0 0 36 36"},t("path",{fill:"#FFCC4D",d:"M36 18c0 9.941-8.059 18-18 18-9.94 0-18-8.059-18-18C0 8.06 8.06 0 18 0c9.941 0 18 8.06 18 18"}),t("ellipse",{fill:"#664500",cx:"18",cy:"27",rx:"5",ry:"6"}),t("path",{fill:"#664500",d:"M5.999 11c-.208 0-.419-.065-.599-.2-.442-.331-.531-.958-.2-1.4C8.462 5.05 12.816 5 13 5c.552 0 1 .448 1 1 0 .551-.445.998-.996 1-.155.002-3.568.086-6.204 3.6-.196.262-.497.4-.801.4zm24.002 0c-.305 0-.604-.138-.801-.4-2.64-3.521-6.061-3.598-6.206-3.6-.55-.006-.994-.456-.991-1.005C22.006 5.444 22.45 5 23 5c.184 0 4.537.05 7.8 4.4.332.442.242 1.069-.2 1.4-.18.135-.39.2-.599.2zm-16.087 4.5l1.793-1.793c.391-.391.391-1.023 0-1.414s-1.023-.391-1.414 0L12.5 14.086l-1.793-1.793c-.391-.391-1.023-.391-1.414 0s-.391 1.023 0 1.414l1.793 1.793-1.793 1.793c-.391.391-.391 1.023 0 1.414.195.195.451.293.707.293s.512-.098.707-.293l1.793-1.793 1.793 1.793c.195.195.451.293.707.293s.512-.098.707-.293c.391-.391.391-1.023 0-1.414L13.914 15.5zm11 0l1.793-1.793c.391-.391.391-1.023 0-1.414s-1.023-.391-1.414 0L23.5 14.086l-1.793-1.793c-.391-.391-1.023-.391-1.414 0s-.391 1.023 0 1.414l1.793 1.793-1.793 1.793c-.391.391-.391 1.023 0 1.414.195.195.451.293.707.293s.512-.098.707-.293l1.793-1.793 1.793 1.793c.195.195.451.293.707.293s.512-.098.707-.293c.391-.391.391-1.023 0-1.414L24.914 15.5z"}))}const Pt=y("result",`
 color: var(--n-text-color);
 line-height: var(--n-line-height);
 font-size: var(--n-font-size);
 transition:
 color .3s var(--n-bezier);
`,[y("result-icon",`
 display: flex;
 justify-content: center;
 transition: color .3s var(--n-bezier);
 `,[M("status-image",`
 font-size: var(--n-icon-size);
 width: 1em;
 height: 1em;
 `),y("base-icon",`
 color: var(--n-icon-color);
 font-size: var(--n-icon-size);
 `)]),y("result-content",{marginTop:"24px"}),y("result-footer",`
 margin-top: 24px;
 text-align: center;
 `),y("result-header",[M("title",`
 margin-top: 16px;
 font-weight: var(--n-title-font-weight);
 transition: color .3s var(--n-bezier);
 text-align: center;
 color: var(--n-title-text-color);
 font-size: var(--n-title-font-size);
 `),M("description",`
 margin-top: 4px;
 text-align: center;
 font-size: var(--n-font-size);
 `)])]),Dt={403:Mt,404:Tt,418:Ht,500:Ot,info:()=>t(ot,null),success:()=>t(tt,null),warning:()=>t(et,null),error:()=>t(Ze,null)},Nt=Object.assign(Object.assign({},X.props),{size:String,status:{type:String,default:"info"},title:String,description:String}),Kt=U({name:"Result",props:Nt,slots:Object,setup(r){const{mergedClsPrefixRef:e,inlineThemeDisabled:i,mergedComponentPropsRef:l}=Q(r),v=R(()=>{var u,h;return r.size||((h=(u=l==null?void 0:l.value)===null||u===void 0?void 0:u.Result)===null||h===void 0?void 0:h.size)||"medium"}),b=X("Result","-result",Pt,Qe,r,e),p=R(()=>{const{status:u}=r,h=v.value,{common:{cubicBezierEaseInOut:z},self:{textColor:E,lineHeight:T,titleTextColor:$,titleFontWeight:x,[A("iconColor",u)]:o,[A("fontSize",h)]:n,[A("titleFontSize",h)]:g,[A("iconSize",h)]:a}}=b.value;return{"--n-bezier":z,"--n-font-size":n,"--n-icon-size":a,"--n-line-height":T,"--n-text-color":E,"--n-title-font-size":g,"--n-title-font-weight":x,"--n-title-text-color":$,"--n-icon-color":o||""}}),f=i?fe("result",R(()=>{const{status:u}=r,h=v.value;let z="";return h&&(z+=h[0]),u&&(z+=u[0]),z}),p,r):void 0;return{mergedClsPrefix:e,cssVars:i?void 0:p,themeClass:f==null?void 0:f.themeClass,onRender:f==null?void 0:f.onRender}},render(){var r;const{status:e,$slots:i,mergedClsPrefix:l,onRender:v}=this;return v==null||v(),t("div",{class:[`${l}-result`,this.themeClass],style:this.cssVars},t("div",{class:`${l}-result-icon`},((r=i.icon)===null||r===void 0?void 0:r.call(i))||t(Ge,{clsPrefix:l},{default:()=>Dt[e]()})),t("div",{class:`${l}-result-header`},this.title?t("div",{class:`${l}-result-header__title`},this.title):null,this.description?t("div",{class:`${l}-result-header__description`},this.description):null),i.default&&t("div",{class:`${l}-result-content`},i),i.footer&&t("div",{class:`${l}-result-footer`},i.footer()))}}),qt=U({__name:"PositionsTableBase",setup(r){const{t:e}=ut(),i=rt(),l=it(),v=nt(),b=B(null),p=B(0),f=B(0),u=B(null),h=B(!1),z=R({get:()=>b.value!=null,set:o=>{o||(b.value=null)}}),E=B([]);function T(o){var n,g,a;return t("div",{style:"padding: 12px 24px; font-size: 13px; line-height: 1.8; display: grid; grid-template-columns: 1fr 1fr; gap: 16px;"},[t("div",{},[t("div",{style:"font-weight: 700; margin-bottom: 8px; color: #0ecb81;"},e("positions.open_info")),t("div",{},e("positions.magic_label")+": "+(o.magic||"-")),t("div",{},e("positions.strategy_label")+": "+(o.comment||o._strategy_name||"-")),t("div",{},e("positions.open_time_label")+": "+se(o,"open_time_ts","open_time")),o.stop_loss?t("div",{},e("positions.sl_distance")+": "+Math.abs(o.open_price-o.stop_loss).toFixed(2)):null,o.take_profit?t("div",{},e("positions.tp_distance")+": "+Math.abs(o.take_profit-o.open_price).toFixed(2)):null]),t("div",{},[t("div",{style:"font-weight: 700; margin-bottom: 8px; color: #f0a020;"},e("positions.status")),t("div",{},e("positions.entry_price_label")+": "+((n=o.open_price)==null?void 0:n.toFixed(2))),t("div",{},e("positions.current_price_label")+": "+((g=o.current_price)==null?void 0:g.toFixed(2))),t("div",{style:{color:o.profit>=0?"#0ecb81":"#f6465d"}},e("positions.floating_pnl")+": "+(o.profit>=0?"+":"")+"$"+((a=o.profit)==null?void 0:a.toFixed(2))),o.stop_loss?t("div",{},e("positions.sl_label")+": "+o.stop_loss.toFixed(2)):null,o.take_profit?t("div",{},e("positions.tp_label")+": "+o.take_profit.toFixed(2)):null])])}const $=[{type:"expand",width:30,renderExpand:T},{title:"Ticket",key:"ticket",width:80},{title:e("positions.strategy"),key:"strategy",width:150,render(o){const n=o.strategy_display||o.comment||o._strategy_name||"",g=o.magic||"",a=n||(g?`Magic ${g}`:"-"),D={H1_v6_hybrid:"#2080f0",M30_rsi_bb:"#f0a020",sanqing_h1:"#9220f0",gold_auto_research:"#20c080",bakome_backup:"#808080",xaubot_backup:"#808080"},N=n.replace(/\s+v[\w.]+$/,"").replace(/_(BUY|SELL)$/,""),S=D[N]||ct(N)||"#808080",s=dt(S),m=t(K,{color:{color:S,textColor:s},size:"small",style:"font-weight: 600;"},{default:()=>a});return o.is_paper?t(q,{size:4,align:"center"},{default:()=>[m,t(K,{type:"warning",size:"tiny"},{default:()=>e("positions.paper_tag")})]}):m}},{title:"TF",key:"timeframe",width:50,render(o){var a;const n=((a=o.strategy)==null?void 0:a.toLowerCase())||"";return n.includes("h4")?"H4":n.includes("h1")?"H1":n.includes("m30")?"M30":n.includes("m15")?"M15":n.includes("m5")?"M5":{gold_auto_research:"H1",h1_breakout:"H1"}[n]||o.timeframe||""}},{title:e("positions.direction"),key:"order_type",width:40,render(o){var g;const n=(g=o.order_type)==null?void 0:g.includes("BUY");return t(K,{type:n?"success":"error",size:"small"},{default:()=>e(n?"positions.buy":"positions.sell")})}},{title:e("positions.volume"),key:"volume",width:40},{title:e("positions.open_price"),key:"open_price",width:80,render(o){var n;return(n=o.open_price)==null?void 0:n.toFixed(2)}},{title:e("positions.current_price"),key:"current_price",width:80,render(o){var n;return(n=o.current_price)==null?void 0:n.toFixed(2)}},{title:e("positions.stop_loss"),key:"stop_loss",width:80,render(o){return o.stop_loss||"-"}},{title:e("positions.take_profit"),key:"take_profit",width:80,render(o){return o.take_profit||"-"}},{title:e("positions.open_time"),key:"open_time",width:120,render(o){return se(o,"open_time_ts","open_time")}},{title:e("positions.profit"),key:"profit",width:80,render(o){const n=o.profit??0;return t("span",{style:{color:n>=0?"#0ecb81":"#f6465d",fontWeight:700}},`${n>=0?"+":""}$${n.toFixed(2)}`)}},{title:e("positions.actions"),key:"actions",width:135,render(o){return t(q,{size:"small"},{default:()=>[t(J,{size:"tiny",secondary:!0,onClick:()=>{b.value=o.ticket,p.value=o.stop_loss||0,f.value=o.take_profit||0}},{default:()=>e("positions.modify_sltp_btn")}),t(J,{size:"tiny",type:"error",secondary:!0,loading:u.value===o.ticket,onClick:()=>{var g;const n=v.warning({title:e("positions.confirm_close"),content:e("positions.confirm_close_msg",{ticket:"#"+o.ticket,direction:(g=o.order_type)!=null&&g.includes("BUY")?e("positions.buy"):e("positions.sell"),volume:o.volume}),positiveText:e("positions.confirm_close"),negativeText:e("common.cancel"),onPositiveClick:async()=>{u.value=o.ticket;try{await i.close(o.ticket),l.success(e("positions.close_success",{ticket:"#"+o.ticket})),n.destroy()}catch(a){a!=null&&a.notFound?l.warning(e("positions.close_not_found",{ticket:"#"+o.ticket})):l.error((a==null?void 0:a.message)||e("positions.close_failed")),n.destroy()}u.value=null},onNegativeClick:()=>{n.destroy()}})}},{default:()=>e("positions.close")})]})}}];async function x(){if(b.value!=null){h.value=!0;try{await lt(b.value,p.value,f.value),l.success(e("positions.modify_sl_tp_updated",{ticket:"#"+b.value})),b.value=null,await i.fetch()}catch(o){l.error((o==null?void 0:o.message)||e("positions.modify_failed"))}h.value=!1}}return(o,n)=>{const g=at;return j(),He("div",null,[_(i).loading?(j(),W(_(ae),{key:0,columns:$,data:[],loading:!0,bordered:!0,"max-height":600})):_(i).items.length===0?(j(),W(_(ht),{key:1,description:o.$t("positions.empty")},{extra:P(()=>[H(_(st),{depth:"3"},{default:P(()=>[oe(re(o.$t("positions.empty_desc")),1)]),_:1})]),_:1},8,["description"])):_(i).error?(j(),W(_(ft),{key:2,type:"error",title:_(i).error,closable:""},null,8,["title"])):(j(),W(_(ae),{key:3,columns:$,data:_(i).items,bordered:!0,"max-height":600,striped:"","single-line":!1,"expanded-row-keys":E.value,"onUpdate:expandedRowKeys":n[0]||(n[0]=a=>E.value=a),"row-key":a=>a.ticket},null,8,["data","expanded-row-keys","row-key"])),H(_(Rt),{show:z.value,"onUpdate:show":n[4]||(n[4]=a=>z.value=a),width:360,placement:"right"},{default:P(()=>[H(_(Et),{title:`${o.$t("positions.modify_sltp")} - #${b.value}`,closable:"",onClose:n[3]||(n[3]=a=>b.value=null)},{default:P(()=>[H(_(q),{vertical:"",size:"large"},{default:P(()=>[H(_(le),{label:o.$t("positions.sl")},{default:P(()=>[H(g,{value:p.value,"onUpdate:value":n[1]||(n[1]=a=>p.value=a),step:.01,style:{width:"100%"}},null,8,["value"])]),_:1},8,["label"]),H(_(le),{label:o.$t("positions.tp")},{default:P(()=>[H(g,{value:f.value,"onUpdate:value":n[2]||(n[2]=a=>f.value=a),step:.01,style:{width:"100%"}},null,8,["value"])]),_:1},8,["label"]),H(_(J),{type:"primary",loading:h.value,onClick:x,block:""},{default:P(()=>[oe(re(o.$t("positions.confirm_modify")),1)]),_:1},8,["loading"])]),_:1})]),_:1},8,["title"])]),_:1},8,["show"])])}}});export{Kt as _,qt as a};
