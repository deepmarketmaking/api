# Installation
1. install PyXLL https://www.pyxll.com/index.html 
2. copy `source` folder to PyXLL installation folder
3. copy configuration from `pyxll.cfg` to PyXLL installation folder
4. open  `pyxll.cfg` and change python path so it points to your python installation. Find variable `executable` and replace pythong path there


# Working in excel
1. open excel and you should see deepmm tab in excel
![](./images/deepmm-in-menu.png?raw=true "")

2. click `deepmm` tab 
3. click configuration button
![](./images/configure-button.png?raw=true "")
4. conect columns in configuration popup. Select identifier column cusip/figi/isin match it with excel column by providing column letter. Next do it for other fields
![](./images/configure-popup.png?raw=true "")
5. Save configuration
6. click on login button
![](./images/login-button.png?raw=true "")
7. provide your email and password and click login
![](./images/login-popup.png?raw=true "")
8. after login you will start syncing data with deepmm. Keep in mind that you need to login every time you open excel.
![](./images/results.png.png?raw=true "")
9. add other worksheets if needed and add configuration for a new worksheet to start syncing data. 
![](./images/configure-button.png?raw=true "")
10. if you don't want to sync data anymore click on "Clear configuration" button
![](./images/clear-configuration.png.png?raw=true "")
11. **connected** status shows your websocket connection status. Keep in mind that it's not related to your login credentials just a status if we were able to connect to websocket server.