a='\xb8\xbb '    #a是<class 'str'>类型
print(type(a),':',a);

#a1=a.encode('gb18030')
#print('a1:',a1);


s1=bytes(a,'raw_unicode_escape')
#s1是<class 'bytes'>类型
print(type(s1),'s1:',s1);


c=s1.decode('gb18030')
#c是<class 'str'>类型
print(type(c),':',c)


a=173
print(a)
b=chr(a);
print(b);

s=str(chr(173).encode());

print(s);