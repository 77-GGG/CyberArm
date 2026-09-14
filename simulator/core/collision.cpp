#include "core.h"
#include <algorithm>
#include <cmath>
#include <vector>
#include <utility>
#include <limits>
namespace {
struct V {double x,y,z;V operator+(V b)const{return {x+b.x,y+b.y,z+b.z};}V operator-(V b)const{return {x-b.x,y-b.y,z-b.z};}V operator*(double s)const{return {x*s,y*s,z*s};}};
double dot(V a,V b){return a.x*b.x+a.y*b.y+a.z*b.z;}
V cross(V a,V b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
V vertex(const double* p){return {p[0],p[1],p[2]};}
V point(const double* t,V p){return {t[0]*p.x+t[1]*p.y+t[2]*p.z+t[3],t[4]*p.x+t[5]*p.y+t[6]*p.z+t[7],t[8]*p.x+t[9]*p.y+t[10]*p.z+t[11]};}
double triangle(V* a,V* b){
 V ea[3],eb[3];for(int i=0;i<3;i++){ea[i]=a[(i+1)%3]-a[i];eb[i]=b[(i+1)%3]-b[i];}
 V na=cross(ea[0],ea[1]),nb=cross(eb[0],eb[1]);V axes[17];int n=0;axes[n++]=na;axes[n++]=nb;
 for(auto x:ea)for(auto y:eb)axes[n++]=cross(x,y);
 for(auto x:ea)axes[n++]=cross(na,x);for(auto y:eb)axes[n++]=cross(nb,y);
 double best=-1e6;bool any=false;
 for(auto axis:axes){double norm=std::sqrt(dot(axis,axis));if(norm<1e-16)continue;any=true;axis=axis*(1/norm);double amin=1e6,amax=-1e6,bmin=1e6,bmax=-1e6;for(int i=0;i<3;i++){double pa=dot(a[i],axis),pb=dot(b[i],axis);amin=std::min(amin,pa);amax=std::max(amax,pa);bmin=std::min(bmin,pb);bmax=std::max(bmax,pb);}best=std::max(best,std::max(amin-bmax,bmin-amax));}
 return any?best:0.;
}
struct B {V c;V axis[3];double half[3];double volume;};
B box(const double* t,const double* bounds){B b;V lo=vertex(bounds),hi=vertex(bounds+3);b.c=point(t,(lo+hi)*.5);for(int i=0;i<3;i++){b.axis[i]={t[i],t[i+4],t[i+8]};b.half[i]=(bounds[i+3]-bounds[i])*.5;}b.volume=b.half[0]*b.half[1]*b.half[2];return b;}
double separation(const B& a,const B& b){V axes[15];int k=0;for(auto x:a.axis)axes[k++]=x;for(auto x:b.axis)axes[k++]=x;for(auto x:a.axis)for(auto y:b.axis)axes[k++]=cross(x,y);double best=-1e6;for(auto axis:axes){double n=std::sqrt(dot(axis,axis));if(n<1e-12)continue;axis=axis*(1/n);double radius=0;for(int i=0;i<3;i++)radius+=std::abs(dot(a.axis[i],axis))*a.half[i]+std::abs(dot(b.axis[i],axis))*b.half[i];best=std::max(best,std::abs(dot(b.c-a.c,axis))-radius);}return best;}
}
double ca_mesh_gap(const double* ta,const double* ba,const int* ca,const int* fa,const double* va,
                   const double* tb,const double* bb,const int* cb,const int* fb,const double* vb,double ceiling){
 try{
  std::vector<std::pair<int,int>> stack;stack.emplace_back(0,0);double best=ceiling;
  while(!stack.empty()){
   auto pair=stack.back();stack.pop_back();int i=pair.first,j=pair.second;
   B a=box(ta,ba+i*6),b=box(tb,bb+j*6);
   if(separation(a,b)>=best)continue;
   bool la=ca[i*2]<0,lb=cb[j*2]<0;
   if(la&&lb){for(int x=0;x<fa[i*2+1];x++)for(int y=0;y<fb[j*2+1];y++){
     V ax[3],by[3];for(int k=0;k<3;k++){ax[k]=point(ta,vertex(va+(fa[i*2]+x)*9+k*3));by[k]=point(tb,vertex(vb+(fb[j*2]+y)*9+k*3));}
     best=std::min(best,triangle(ax,by));if(best<=.0002)return best;
    }}
   else if(lb||(!la&&a.volume>=b.volume)){stack.emplace_back(ca[i*2],j);stack.emplace_back(ca[i*2+1],j);}
   else {stack.emplace_back(i,cb[j*2]);stack.emplace_back(i,cb[j*2+1]);}
  }return best;
 }catch(...){return -std::numeric_limits<double>::infinity();}
}
