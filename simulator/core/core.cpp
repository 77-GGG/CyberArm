#include "core.h"
#include <cmath>
#include <algorithm>
#include <cstring>

namespace {
void eye(double* a){std::fill(a,a+16,0.0);a[0]=a[5]=a[10]=a[15]=1;}
void mul(const double* a,const double* b,double* out){double r[16]={};for(int i=0;i<4;i++)for(int j=0;j<4;j++)for(int k=0;k<4;k++)r[4*i+j]+=a[4*i+k]*b[4*k+j];std::copy(r,r+16,out);}
void ry(double t,double x,double y,double z,double* m){eye(m);m[0]=m[10]=std::cos(t);m[2]=std::sin(t);m[8]=-std::sin(t);m[3]=x;m[7]=y;m[11]=z;}
double clamp(double x){return std::max(0.0,std::min(1.0,x));}
double dot(const double* a,const double* b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
}
int ca_fk(const double* q,const double* joints,const double* palm,const double* tool,double* frames,double* tcp){
 if(!q||!joints||!palm||!tool||!frames||!tcp)return -1;
 for(int i=0;i<6;i++)if(!std::isfinite(q[i]))return -2;
 double previous[16];eye(previous);
 for(int i=0;i<5;i++){
   double r[16],f[16];eye(r);r[0]=r[5]=std::cos(q[i]);r[1]=-std::sin(q[i]);r[4]=std::sin(q[i]);
   mul(previous,joints+16*i,f);mul(f,r,frames+16*i);std::copy(frames+16*i,frames+16*(i+1),previous);
 }
 mul(frames+64,palm,frames+80);mul(frames+80,tool,tcp);
 for(int side=0;side<2;side++){
   const double sg=side==0?1:-1, ax=side==0?.013:.023, gx=side==0?.005:.0319;
   const double theta=(side==0?-155:147.5)*3.14159265358979323846/180+sg*q[5];
   const double dx=side==0?.03075:-.030486231,dz=side==0?0:.00401368;
   const double cx=gx+dx*std::cos(theta)+dz*std::sin(theta),cz=-.025-dx*std::sin(theta)+dz*std::cos(theta);
   const double ex=ax-cx,ez=-.005-cz,d=std::sqrt(ex*ex+ez*ez);
   if(d<.009||d>.053)return -3;
   const double a=(.022*.022-.031*.031+d*d)/(2*d),h2=.022*.022-a*a;
   if(h2< -1e-12)return -3;
   const double h=std::sqrt(std::max(0.0,h2)),bx=cx+a*ex/d-sg*h*ez/d,bz=cz+a*ez/d+sg*h*ex/d;
   double g[16];const int base=6+5*side;
   ry(theta,gx,.0084,-.025,g);mul(frames+80,g,frames+16*base);
   ry(std::atan2(-(bz+.005),bx-ax),ax,.0084,-.005,g);mul(frames+80,g,frames+16*(base+1));
   ry(std::atan2(cx-bx,cz-bz),cx,.0128,cz,g);mul(frames+80,g,frames+16*(base+2));
   ry(0,cx,.0118,cz,g);mul(frames+80,g,frames+16*(base+3));
   ry(0,bx,.0118,bz,g);mul(frames+80,g,frames+16*(base+4));
 }
 return 0;
}
int ca_curve(double t,double duration,double* out){
 if(!out||!std::isfinite(t)||!std::isfinite(duration)||duration<=0)return -1;
 const double u=clamp(t/duration),u2=u*u,u3=u2*u;
 out[0]=u3*(10+u*(-15+6*u));out[1]=30*u2*(1-u)*(1-u)/duration;
 out[2]=60*u*(1-u)*(1-2*u)/(duration*duration);return 0;
}
double ca_segment_distance(const double* p,const double* q,const double* r,const double* s){
 double u[3],v[3],w[3];for(int i=0;i<3;i++){u[i]=q[i]-p[i];v[i]=s[i]-r[i];w[i]=p[i]-r[i];}
 double a=dot(u,u),b=dot(u,v),c=dot(v,v),d=dot(u,w),e=dot(v,w),x=0,y=0;
 if(a<1e-18){y=c<1e-18?0:clamp(e/c);}else if(c<1e-18){x=clamp(-d/a);}else{
  double den=a*c-b*b;x=den>1e-18?clamp((b*e-c*d)/den):0;y=(b*x+e)/c;
  if(y<0){y=0;x=clamp(-d/a);}else if(y>1){y=1;x=clamp((b-d)/a);}
 }
 double dist=0;for(int i=0;i<3;i++){double z=w[i]+x*u[i]-y*v[i];dist+=z*z;}return std::sqrt(dist);
}
