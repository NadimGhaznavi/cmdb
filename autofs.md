### Introduction and Scope

This page documents the **Autofs** configuration on my network.


### Installing the AutoFS Software

Use the command below to install the **Autofs** software:
```
sudo apt install autofs
```

### Automatically Start the Autofs Software at Boot Time

Use the commands below to automatically start the **Autofs** software at boot time.
```
systemctl enable autofs
```

### Manually Starting the Autofs Software

Use the command below to manually start **Autofs**.
```
systemctl start autofs
```

### /etc/auto.master

A complete listing of the `/etc/auto.master` file is shown below. This file should be owned by the *root* user.
```
+auto.master
/imports	/etc/auto.imports
```

### /etc/auto.imports

The `/etc/auto.imports` file, referenced by the `/etc/auto.master` defines the file shares. This file should
be owned by root. A complete listing is shown below.
```
old	-rw,soft,rsize=8192,wsize=8192	kermit.osoyalce.com:/exports/old
new     -rw,soft,rsize=8192,wsize=8192	kermit.osoyalce.com:/exports/new
film    -rw,soft,rsize=8192,wsize=8192	kermit.osoyalce.com:/exports/old/archive/film
```
