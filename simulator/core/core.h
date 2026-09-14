#pragma once
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C"
#endif
// Matrices are row-major double[16], translations in metres. q is radians.
API int ca_fk(const double* q, const double* joints, const double* palm,
              const double* tool, double* frames, double* tcp);
API int ca_curve(double t, double duration, double* value_velocity_acceleration);
API double ca_segment_distance(const double* a, const double* b, const double* c, const double* d);
API double ca_mesh_gap(const double* ta,const double* ba,const int* ca,const int* fa,const double* va,
                      const double* tb,const double* bb,const int* cb,const int* fb,const double* vb,double ceiling);
