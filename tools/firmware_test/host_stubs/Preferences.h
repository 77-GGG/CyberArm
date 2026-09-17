#pragma once
#include <map>
#include <string>
#include <vector>
#include <cstring>
class Preferences {
 public:
  static inline std::map<std::string,std::vector<unsigned char>> data;
  static inline bool failWrite=false;
  bool begin(const char*,bool){return true;}
  size_t getBytesLength(const char* key){return data[key].size();}
  size_t putBytes(const char* key,const void* p,size_t size){
    if(failWrite)return 0;
    data[key]=std::vector<unsigned char>((const unsigned char*)p,(const unsigned char*)p+size);return size;
  }
  size_t getBytes(const char* key,void* p,size_t size){
    const auto& d=data[key];if(d.size()!=size)return 0;std::memcpy(p,d.data(),size);return size;
  }
};
