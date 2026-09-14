#include "core.h"
#include <cmath>
#include <limits>
int main(){double v[3];if(ca_curve(0,2,v)||v[0]!=0||v[1]!=0)return 1;
 if(ca_curve(2,2,v)||std::abs(v[0]-1)>1e-14||v[1]!=0)return 2;
 if(ca_curve(1,2,v)||std::abs(v[0]-.5)>1e-14)return 3;
 if(ca_curve(1,0,v)==0||ca_curve(std::numeric_limits<double>::quiet_NaN(),1,v)==0)return 4;
 double a[]={0,0,0},b[]={1,0,0},c[]={.5,1,0},d[]={.5,-1,0};
 if(ca_segment_distance(a,b,c,d)>1e-12)return 5;return 0;}
