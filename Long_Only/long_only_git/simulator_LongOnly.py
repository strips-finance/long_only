import numpy as np 
import pandas as pd
import random 
import json 
import requests 
import warnings 
warnings.filterwarnings('ignore')
import itertools
import os
import math
from datetime import datetime
import math 
from matplotlib import pyplot as plt
import sys
from openpyxl import load_workbook
"""getting APY data
# Obtain historical lending rate
class DPAPI:
    def __init__(self,url):
        self._url = url
    @property 
    def url(self):
        return self._url
    def get_url(self):
        return requests.get(self.url)
    def get_data(self):
        response = self.get_url()
        return json.loads(response.content)
if __name__ =='__main__':
    url = 'https://data-api.defipulse.com/api/v1/defipulse/api/getLendingHistory?api-key=e837cb65f0b652eee0b7b8754088c9580ee13b3b89c78716d0cecf0b5d2b'
    dpapi = DPAPI(url)
    json_data=dpapi.get_data()
#Analysis
time = []
for i in range(0,len(json_data)):
    try:
        time.append(datetime.fromtimestamp(int(json_data[i]['timestamp'])).strftime('%Y-%m-%d'))
    except ValueError: 
        pass
apy_history = pd.DataFrame(columns =['aave','compound','dydx'],index=[i for i in time])
for i in range(0,len(json_data)):
    try: 
        apy_history.iloc[i,0]=json_data[i]['lend_rates']['aave']
        apy_history.iloc[i,1]=json_data[i]['lend_rates']['compound']
        apy_history.iloc[i,2]=json_data[i]['lend_rates']['dydx']
    except ValueError: 
        pass
#Pause
apy_history = apy_history.reindex(index=apy_history.index[::-1])
apy_history = apy_history.dropna()    
apy_history.to_excel('apy_history.xlsx')
"""
"""APY history"""
apy_history = pd.read_excel('apy_history.xlsx',index_col=0,engine='openpyxl')
binance_history =pd.read_csv('funding_rates_binance.csv',index_col=0)
binance_history.index = pd.to_datetime(binance_history.index).strftime('%Y-%m-%d')
binance_history = binance_history.groupby(binance_history.index).mean()
binance_history['Funding Rate']=binance_history['Funding Rate']*3*365*100
apy_history = pd.merge(left=apy_history, left_index=True, right=binance_history,right_index=True, how='inner')

ftx_history = pd.read_csv('funding_rates_ftx.csv',index_col=0)
ftx_history.index = pd.to_datetime(ftx_history.index).strftime('%Y-%m-%d-%H:%M:%S')
ftx_history = ftx_history.reset_index().drop_duplicates().set_index('Time')
ftx_history.index = pd.to_datetime(ftx_history.index).strftime('%Y-%m-%d')
ftx_history = ftx_history.groupby(ftx_history.index).mean()
ftx_history['Rate']=ftx_history['Rate']*24*365*100
apy_history = pd.merge(left=apy_history, left_index=True, right=ftx_history,right_index=True, how='inner')
apy_history.rename(columns = {'Funding Rate':'binance','Rate':'ftx'}, inplace = True)
#get the trailing_average_30d
apy_history_trailing = apy_history.rolling(30,min_periods =1).mean()
btc_history = pd.read_csv('BTC-USD.csv',index_col=0)

"""set the Variable combination matrix"""
liquidation_level=0.05 # if liquiidation level need to be higher for stressed market
initial_haircut=0.5 #if AMM is sensitive to initial haircut set and how long does it converge
duration = 'calcUnrealized_perp' # if AMM Realized PnL is sensitive to "perpetual" vs. 1 year contract 
virtual_liquidity = 500000
withdraw_fee = [0]
method =['lpPrice_exUnrealized']
lists = [withdraw_fee,method]
combo_mix = pd.DataFrame(list(itertools.product(*lists)),columns = ['withdraw_fee%','method'])

amm_performance = combo_mix.copy()
amm_performance[['revenue','Realized_PnL','Unrealized_PnL',\
                 'liquidated_count','rejected_count','total_return','AMM_ROI','net_return','Strips_ROI',\
                     'Sharp_Ratio_amm','Sharp_Ratio_Strips']]=0.0

#len(combo_mix)
for n in range(0,len(combo_mix)):
    withdraw_fee = combo_mix.iloc[n,0]
    method = combo_mix.iloc[n,1]
    
    def calcRealized_perp(i):#self is vault[pair] #on notional of the trad    
        if vault[pair]['avg_price'][i-1]!=0.0:
            #because this trader has an open position, then elased day +1 from previous date
            if vault[pair]['side'][i-1]==-1:
                #trader is short, so they receive fixed(trading PnL positive when rate is lower)
                #if trader chooses to hold until maturity (365 days), then trader will simply pay the fixed rate at entry level 
                #short means side is (-1)*(-entry level rate) will get a POSITIVE trading PnL = received fixed rate
                vault[pair]['realized_trading_PnL'][i]=0.0
                vault[pair]['realized_trading_PnL'][i]=1*(vault[pair]['avg_price'][i-1]*0.01-amm[pair]['Quote_initial'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)*vault[pair]['notional'][i]
                #trader pay floating(pay funding PnL since inception 
                date = i
                vault[pair]['realized_funding_PnL'][i]=0.0
                for k in range(1,int(vault[pair]['days_elapsed'][i])+1):   
                    #keep adding payments
                    vault[pair]['realized_funding_PnL'][i]+=-1*(apy_history[pair][date-1]-vault[pair]['avg_price'][date-1])*1/30*0.01*vault[pair]['notional'][i]
                    date = date -1 
            elif vault[pair]['side'][i-1]==1:
                #trader is long, so they receive floating (trading PnL positive when rate is higher)
                #trader pay fixed (trading PnL)
                #if trader chooses to hold until maturity (365 days), then trader will simply receive initial fixed rate at entry level 
                #long means side is (+1)*(-entry level rate) will get a NEGATIVE trading PnL = pay fixed rate 
                #trader pay fixed (pay trading PnL)
                vault[pair]['realized_trading_PnL'][i]=0.0
                vault[pair]['realized_trading_PnL'][i]=-1*(vault[pair]['avg_price'][i]*0.01-amm[pair]['Quote_initial'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)*vault[pair]['notional'][i]
                print('within function: '+str(pair))
                #trader receive floating(receive funding PnL)
                date = i
                vault[pair]['realized_funding_PnL'][i]=0.0
                for k in range(1,int(vault[pair]['days_elapsed'][i])+1):
                    vault[pair]['realized_funding_PnL'][i]+=1*(apy_history[pair][date-1]-vault[pair]['avg_price'][date-1])*1/30*0.01*vault[pair]['notional'][i]
                    date = date -1 
            #aggregate unrealized PnL    
            return (vault[pair]['realized_trading_PnL'][i]+vault[pair]['realized_funding_PnL'][i])    
    
    def calcUnrealized_perp(self,i):#self is vault[pair] # on position per market 
        if vault[pair]['avg_price'][i-1]!=0.0:
            #because this trader has an open position, then elased day +1 from previous date
            if self['side'][i-1]==-1:
                #trader is short, so they receive fixed(trading PnL positive when rate is lower)
                #if trader chooses to hold until maturity (365 days), then trader will simply pay the fixed rate at entry level 
                #short means side is (-1)*(-entry level rate) will get a POSITIVE trading PnL = received fixed rate
                self['trading_PnL'][i]=0.0
                self['trading_PnL'][i]=1*(self['avg_price'][i]*0.01-amm[pair]['Quote_initial'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)*self['position'][i]  
                #trader pay floating(pay funding PnL based on different period of average price) 
                date = i
                self['funding_PnL'][i]=0.0
                for k in range(1,int(self['days_elapsed'][i])+1):   
                    #keep adding payments
                    self['funding_PnL'][i]+=-1*(apy_history[pair][date-1]-self['avg_price'][date-1])*1/30*0.01*self['position'][date]
                    date = date -1 
            elif self['side'][i-1]==1:
                #trader is long, so they receive floating (trading PnL positive when rate is higher)
                #trader pay fixed (trading PnL)
                #if trader chooses to hold until maturity (365 days), then trader will simply receive initial fixed rate at entry level 
                #long means side is (+1)*(-entry level rate) will get a NEGATIVE trading PnL = pay fixed rate 
                #trader pay fixed (pay trading PnL)
                self['trading_PnL'][i]=0.0
                self['trading_PnL'][i]=-1*(self['avg_price'][i]*0.01-amm[pair]['Quote_initial'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)*self['position'][i]
                #trader receive floating(receive funding PnL)
                date = i
                self['funding_PnL'][i]=0.0
                for k in range(1,int(self['days_elapsed'][i])+1):
                    self['funding_PnL'][i]+=1*(apy_history[pair][date-1]-self['avg_price'][date-1])*1/30*0.01*self['position'][date]
                    date = date -1 
            #aggregate unrealized PnL    
            return (self['trading_PnL'][i]+self['funding_PnL'][i])    
    
    
    def calcUnrealized_perp_traders(self,i):
        if self['entry_lvl'][i-1]!=0.0:
            pair = self['currency'][i-1]
            #because this trader has an open position, then elased day +1 from previous date
            self['days_elapsed'][i]=self['days_elapsed'][i-1]+1
            if self['side'][i-1]==-1:
                #trader is short, so they receive fixed(trading PnL positive when rate is lower)
                #if trader chooses to hold until maturity (365 days), then trader will simply pay the fixed rate at entry level 
                #short means side is (-1)*(-entry level rate) will get a POSITIVE trading PnL = received fixed rate
                self['trading_PnL'][i]=0.0
                self['trading_PnL'][i]=1*(self['entry_lvl'][i-1]*0.01-amm[pair]['Quote_initial'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)*self['notional'][i-1]
                #trader pay floating(pay funding PnL since inception 
                date = i
                self['funding_PnL'][i]=0.0
                for k in range(1,int(self['days_elapsed'][i])+1):   
                    #keep adding payments
                    self['funding_PnL'][i]+=-1*(apy_history[pair][date-1]-self['entry_lvl'][i-1])*1/30*0.01*self['notional'][i-1]
                    date = date -1 
            elif self['side'][i-1]==1:
                #trader is long, so they receive floating (trading PnL positive when rate is higher)
                #trader pay fixed (trading PnL)
                #if trader chooses to hold until maturity (365 days), then trader will simply receive initial fixed rate at entry level 
                #long means side is (+1)*(-entry level rate) will get a NEGATIVE trading PnL = pay fixed rate 
                #trader pay fixed (pay trading PnL)
                self['trading_PnL'][i]=0.0
                self['trading_PnL'][i]=-1*(self['entry_lvl'][i-1]*0.01-amm[pair]['Quote_initial'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)*self['notional'][i-1]
                #trader receive floating(receive funding PnL)
                date = i
                self['funding_PnL'][i]=0.0
                for k in range(1,int(self['days_elapsed'][i])+1):
                    self['funding_PnL'][i]+=1*(apy_history[pair][date-1]-self['entry_lvl'][i-1])*1/30*0.01*self['notional'][i-1]
                    date = date -1 
            #aggregate unrealized PnL    
            return (self['trading_PnL'][i]+self['funding_PnL'][i])    
    
    def updateAMM(self,i):#self is amm[pair] right after each trader's each trade 
        #AMM only gets 75% of trading fee_in
        self['Staked_amount'][i]=virtual_liquidity+self['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+self['USDC_Balance'][i]
        self['Staked_amount_Long'][i] += (self['USDC_Balance'][i]-pre_usdc_value) *(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
        self['Staked_amount_Short'][i] += (self['USDC_Balance'][i]-pre_usdc_value) *1/(1+amm[pair]['Ratio'][i])
        self['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
        self['Quote_initial'][i]=apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
        
    def updateTradingVolume(i):
        vault[pair]['cumulative_Trading_vol'][i] = vault[pair]['notional'][i] #only accumulate every 1 day, no need to add from prev days
        vault[pair]['Rebalance_count'][i]+=1
        amm[pair]['cumulative_Trading_Vol_rebased_agg'][i] +=vault[pair]['cumulative_Trading_vol'][i]
        
    def updateTradingVolume_traders(self,i,j):#self is traders[j] right after each trader's trade #after traders open new position or close/liquidate positions 
    #check if this trader stakes in the same market or not, staking in other markets would not boost the volume
        if (stakers[j]['currency'][i] == traders[j]['currency'][i]) & (stakers[j]['currency'][i]!=str(0.0)):
            #since stakers currenty = traders currency,we can directly use amm[pair]
            stakers[j]['Share_Percentage'][i]=stakers[j]['Staked_LP_Token'][i]/amm[pair]['Staked_amount_LP_token'][i]
        else: 
            stakers[j]['Share_Percentage'][i]=0
        self['Trading_Vol_rebased_'+pair][i]= self['notional'][i-1]*(1+stakers[j]['Share_Percentage'][i])
        #since we resets trading volume every 24 hours, so we don't accumulate anymore 
        #self['cumulative_Trading_Vol_rebased_'+pair][i]=self['cumulative_Trading_Vol_rebased_'+pair][i-1]
        self['cumulative_Trading_Vol_rebased_'+pair][i]+=self['Trading_Vol_rebased_'+pair][i]
        self['count_trades'][i]+=1
        self['average_trading_period'][i]=self['notional'][i-1]*self['days_elapsed'][i]/self['notional'][i-1]
       
        #update cumulative trading volume and rebased cumulative trading volume for amm
        #no need to inheret as of traders since we already inheret at beginning of each day 
        amm[pair]['cumulative_Trading_Vol_rebased_agg'][i]+=self['Trading_Vol_rebased_'+pair][i]    
        amm[pair]['average_trading_period'][i]=np.nanmean([amm[pair]['average_trading_period'][i],self['average_trading_period'][i]])
    
    def buySTRP_uniswap(i):#amount is only for restake
        #traders can choose to buy STRP tokens in order to get LP tokens
        value = np.random.randint(1000,10000)
        amount = value / uniswap_market['STRP_Price'][i]
        STRP_amount_change =0.0
        USDC_amount_change =0.0
        while uniswap_market['STRP_Inventory'][i]-amount <0.8*uniswap_market['STRP_Inventory'][i]: #cannot buy mroe than 20% of market inventory 
            amount = np.random.randint(100,1000)
        constant =  uniswap_market['STRP_Inventory'][i]* uniswap_market['USDC_Inventory'][i]#constant k before change
        uniswap_market['STRP_Inventory'][i]-=amount #since the buyer bought some STRP, then inventory would decrease
        uniswap_market['USDC_Inventory'][i] = constant/uniswap_market['STRP_Inventory'][i]#since it is 50/50, USDC inventory would increase 
        uniswap_market['STRP_Price'][i]=uniswap_market['USDC_Inventory'][i]/uniswap_market['STRP_Inventory'][i]
        uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
            /uniswap_market['LP_Token_amount'][i]    
        #then assuming this person has additional USDC available for the STRP he just bought + STRP received as reward (if any)  and want to mint LP tokens 
        """first liquidity providing - liquidity = sqrt(x0*y0) - min where min = 1000
        else: liquidity = min((x0/reserve0*totalsupply), (y0/reserve1*totalsupply)) 
        liquidity injection = same proprotion as of the current reserve"""
        # x0/y0 = reserves 0/reserves1
        # y0 = x0 * (reserves 1/ reserves 0) = x0* proportion 
        # proportion is based on the current reserves, before new staking into liquidity pool 
        #after buying STRP tokens for amount (without restake_amount which is already minted), this new inventory is updated 
        proportion = uniswap_market['USDC_Inventory'][i]/uniswap_market['STRP_Inventory'][i] 
        STRP_amount_change = amount
        USDC_amount_change = STRP_amount_change * proportion #y0=x0 * proportion     
        uniswap_market['STRP_Inventory'][i]+=STRP_amount_change #just bouhgt from the market, add it back 
        uniswap_market['USDC_Inventory'][i]+=USDC_amount_change #assume this person has additional USDC to stake LP tokens              
        lp_token_minted = min(STRP_amount_change/uniswap_market['STRP_Inventory'][i]*uniswap_market['LP_Token_amount'][i],\
                              USDC_amount_change/uniswap_market['USDC_Inventory'][i]*uniswap_market['LP_Token_amount'][i])
        uniswap_market['LP_Token_amount'][i]+=lp_token_minted
        uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
            /uniswap_market['LP_Token_amount'][i]
        return (lp_token_minted)
    
    def checkIPLoss(self,i):
        if i<=10:
            profit_staking = ((self['Realized_PnL'][i]+self['revenue'][i]+self['Unrealized_PnL'][i])-\
                              (self['Realized_PnL'][0]+self['revenue'][0]+self['Unrealized_PnL'][0]))\
                /abs(self['Realized_PnL'][0]+self['revenue'][0]+self['Unrealized_PnL'][0]) 
            profit_holding = (uniswap_market['STRP_Price'][i]-uniswap_market['STRP_Price'][0])/uniswap_market['STRP_Price'][0]-\
                (uniswap_market['LP_Token_Price'][i]-uniswap_market['LP_Token_Price'][0])/uniswap_market['LP_Token_Price'][0]
        else: 
            profit_staking = ((self['Realized_PnL'][i]+self['revenue'][i]+self['Unrealized_PnL'][i])-\
                              (self['Realized_PnL'][i-10]+self['revenue'][i-10]+self['Unrealized_PnL'][i-10]))\
                /abs(self['Realized_PnL'][i-10]+self['revenue'][i-10]+self['Unrealized_PnL'][i-10]) 
            profit_holding = (uniswap_market['STRP_Price'][i]-uniswap_market['STRP_Price'][i-10])/uniswap_market['STRP_Price'][i-10]-\
                (uniswap_market['LP_Token_Price'][i]-uniswap_market['LP_Token_Price'][i-10])/uniswap_market['LP_Token_Price'][i-10]
        return (profit_staking - profit_holding)
    
    def burnLP_uniswap(self,i):#after stakers unstaking, will burn LP tokens on uniswap and then randomly choose whether holding or selling STRP tokens 
        lp_token_burnt = self['LP_Token_received'][i]/uniswap_market['LP_Token_amount'][i]
        STRP_amount_change = lp_token_burnt/uniswap_market['LP_Token_amount'][i] * uniswap_market['STRP_Inventory'][i]
        USDC_amount_change = lp_token_burnt/uniswap_market['LP_Token_amount'][i] * uniswap_market['USDC_Inventory'][i]
        uniswap_market['STRP_Inventory'][i]-=STRP_amount_change #less staking 
        uniswap_market['USDC_Inventory'][i]-=USDC_amount_change
        uniswap_market['LP_Token_amount'][i] -= lp_token_burnt
        #random draw if hold or sell STRP tokens after unstaking 
        if bool(random.getrandbits(1)):
            #uniswap LP will get additional STRP by buying STRP from the seller (STRP inventory increase and price drops )
            constant =  uniswap_market['STRP_Inventory'][i]* uniswap_market['USDC_Inventory'][i]#constant k before change 
            uniswap_market['STRP_Inventory'][i]-=STRP_amount_change #received after burning the LP tokens 
            uniswap_market['USDC_Inventory'][i] = constant/uniswap_market['STRP_Inventory'][i]#since it is 50/50
            uniswap_market['STRP_Price'][i]=uniswap_market['USDC_Inventory'][i]/uniswap_market['STRP_Inventory'][i]
            uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
                /uniswap_market['LP_Token_amount'][i]    
    
    
    def entry_ratio(i):
        if amm[pair]['Quote_initial'][i]<amm[pair]['apy_history'][i]:
            entry_ratio = 0.7
        else: 
            entry_ratio = 0.3
        return entry_ratio
    def long_ratio(i):
        if amm[pair]['Quote_initial'][i]<amm[pair]['apy_history'][i]:
            long_ratio = 0.7
        else: 
            long_ratio = 0.3
        return long_ratio
    
    #the script for leveragedCarry
    
    
    def longOnlyVault(i):#self = vault[pair] 
        for pair in currencies:
             vault[pair]['apy_history'][i] = apy_history[pair][i]
             vault[pair]['instant_carry%'][i]= (apy_history[pair][i]-amm[pair]['Quote_initial'][i]) #instant carry if long or short at the current market level 
             vault[pair]['expected_return'][i]=vault[pair]['instant_carry%'][i]
             #if trader = long, then maxNotional = 0.1* (real TVL+net exposure of AMM + unrealized PnL)
             #if trader = short, then maxNotional = 0.1* (real TVL - net exposure of AMM + unrealized PnL)        
             if vault[pair]['expected_return'][i]>0:
                 vault[pair]['maxNotional'][i] = 0.1*(amm[pair]['Staked_amount'][i]+amm[pair]['net_exposure'][i]+amm[pair]['Unrealized_PnL'][i])
                 vault[pair]['side'][i]=1
                 vault_summary['countPositiveCarry'][i]+=1
        for pair in currencies:
            if vault[pair]['expected_return'][i]>0:
                vault_summary['averageCarry%'][i] += vault[pair]['expected_return'][i]/vault_summary['countPositiveCarry'][i] #running average
        for pair in currencies:
            if vault[pair]['expected_return'][i]>0:
                vault[pair]['vector'][i] = math.exp(vault[pair]['expected_return'][i]/vault_summary['averageCarry%'][i])
                vault_summary['vector_sum'][i] += vault[pair]['vector'][i]
        for pair in currencies:
            vault[pair]['weight%'][i] = vault[pair]['vector'][i]/vault_summary['vector_sum'][i]
            vault[pair]['targetAllocation'][i] = vault[pair]['weight%'][i] *vault_summary['Cash_reserves'][i]
        
        for pair in currencies:
            if i == 0:       
                print('daily rebal for pair: '+pair)
                #only trade market with positive carry with leverage = 1x
                if vault[pair]['expected_return'][i]>0: 
                    vault[pair]['side'][i]=1
                    vault[pair]['notional'][i] = min(vault[pair]['maxNotional'][i],vault[pair]['targetAllocation'][i])
                    vault[pair]['collateral'][i] = vault[pair]['notional'][i]/3
                    vault[pair]['position'][i] = vault[pair]['notional'][i]
                    amm[pair]['Staked_amount_Long'][i]+= vault[pair]['notional'][i]
                    amm[pair]['net_exposure'][i] -= vault[pair]['notional'][i]
                else:
                    #do nothing if carry is not high enough (to leave some buffer)
                    vault[pair]['side'][i]=0 
                    vault[pair]['notional'][i]=0
                    vault[pair]['collateral'][i]=0
                    vault[pair]['position'][i]=0
                amm[pair]['Ratio'][i]=amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                amm[pair]['Quote_initial'][i]= apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                vault[pair]['avg_price'][i]=amm[pair]['Quote_initial'][i]
                vault[pair]['cumulative_Trading_vol'][i] = vault[pair]['notional'][i] #because rewards only give out on daily basis 
                amm[pair]['cumulative_Trading_Vol_rebased_agg'][i] += vault[pair]['notional'][i]
    
                #update the trading income into AMM 
                vault[pair]['trading_fee_in'][i]=vault[pair]['notional'][i]*vault[pair]['avg_price'][i]*0.01*0.01
                vault_summary['Cash_reserves'][i] -= vault[pair]['trading_fee_in'][i]
                vault_summary['USDC_Balance'][i] -=vault[pair]['trading_fee_in'][i]
                vault_summary['Cash_reserves'][i] -= vault[pair]['collateral'][i]
                vault_summary['USDC_Balance'][i] -= vault[pair]['collateral'][i]
                """updatee revenue, USDC_balance and staking amount of AMM, TL and TS for the next trader"""
                #AMM only gets 75% of trading fee_in
                amm[pair]['revenue'][i]+=vault[pair]['trading_fee_in'][i]*0.75
                amm[pair]['USDC_Balance'][i]+=vault[pair]['trading_fee_in'][i]*0.75
                amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['revenue'][i] \
                #there is no realized pnl in day 1 
                amm[pair]['Staked_amount_Long'][i]+=vault[pair]['trading_fee_in'][i]*0.75*(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
                amm[pair]['Staked_amount_Short'][i]+=vault[pair]['trading_fee_in'][i]*0.75*1/(1+amm[pair]['Ratio'][i])
                amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                amm[pair]['Quote_initial'][i]=(apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
                #Insurance pool gets 5% of trading fee_in and 20% goes to governence 
                insurance['trading_fee'][i]+=vault[pair]['trading_fee_in'][i]*0.25
                amm[pair]['apy_history'][i]=apy_history[pair][i]        
            elif i>0:
              #no existing position 
                if vault[pair]['position'][i-1] == 0.0: 
                    vault[pair]['Rebal_size'][i] = vault[pair]['targetAllocation'][i] - vault[pair]['position'][i-1]
                #open new (same as day 0)
                    if vault[pair]['expected_return'][i]>0: 
                        vault[pair]['side'][i]=1
                        vault[pair]['notional'][i] = min(vault[pair]['maxNotional'][i],vault[pair]['targetAllocation'][i])#here targetAllocation == Rebal_size, since vault[pair]['position'][i]==0
                        vault[pair]['collateral'][i] = vault[pair]['notional'][i]/3
                        vault[pair]['position'][i] = vault[pair]['notional'][i]
                        amm[pair]['Staked_amount_Long'][i]+= vault[pair]['notional'][i]
                        amm[pair]['net_exposure'][i] -= vault[pair]['notional'][i]
                    else:
                        #do nothing if carry is not high enough (to leave some buffer)
                        vault[pair]['side'][i]=0 
                        vault[pair]['notional'][i]=0
                        vault[pair]['collateral'][i]=0
                        vault[pair]['position'][i]=0
                    amm[pair]['Ratio'][i]=amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                    amm[pair]['Quote_initial'][i]= apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                    vault[pair]['avg_price'][i]=amm[pair]['Quote_initial'][i]
                    vault[pair]['cumulative_Trading_vol'][i] = vault[pair]['notional'][i] #because rewards only give out on daily basis 
                    amm[pair]['cumulative_Trading_Vol_rebased_agg'][i] += vault[pair]['notional'][i]
                    #update the trading income into AMM 
                    vault[pair]['trading_fee_in'][i]=vault[pair]['notional'][i]*vault[pair]['avg_price'][i]*0.01*0.01
                    vault_summary['Cash_reserves'][i] -= vault[pair]['trading_fee_in'][i]
                    vault_summary['USDC_Balance'][i] -=vault[pair]['trading_fee_in'][i]
                    vault_summary['Cash_reserves'][i] -= vault[pair]['collateral'][i]
                    vault_summary['USDC_Balance'][i] -= vault[pair]['collateral'][i]
                    """updatee revenue, USDC_balance and staking amount of AMM, TL and TS for the next trader"""
                    #AMM only gets 75% of trading fee_in
                    amm[pair]['revenue'][i]+=vault[pair]['trading_fee_in'][i]*0.75
                    amm[pair]['USDC_Balance'][i]+=vault[pair]['trading_fee_in'][i]*0.75
                    amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['revenue'][i] \
                    #there is no realized pnl in day 1 
                    amm[pair]['Staked_amount_Long'][i]+=vault[pair]['trading_fee_in'][i]*0.75*(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
                    amm[pair]['Staked_amount_Short'][i]+=vault[pair]['trading_fee_in'][i]*0.75*1/(1+amm[pair]['Ratio'][i])
                    amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                    amm[pair]['Quote_initial'][i]=(apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
                    #Insurance pool gets 5% of trading fee_in and 20% goes to governence 
                    insurance['trading_fee'][i]+=vault[pair]['trading_fee_in'][i]*0.25
                    amm[pair]['apy_history'][i]=apy_history[pair][i]        
                        
                #there is open position 
                elif vault[pair]['position'][i-1] != 0.0:
                    vault[pair]['position'][i] = vault[pair]['position'][i-1]
                    vault[pair]['collateral'][i] = vault[pair]['collateral'][i-1]
                    vault[pair]['avg_price'][i] = vault[pair]['avg_price'][i-1]
                    #rebalance
                    vault[pair]['Rebal_size'][i] = vault[pair]['targetAllocation'][i] - vault[pair]['position'][i]
                    #add more 
                    if vault[pair]['Rebal_size'][i]>0:                    
                        vault[pair]['side'][i]=1
                        vault[pair]['notional'][i] = min(vault[pair]['Rebal_size'][i],vault[pair]['maxNotional'][i])
                        amm[pair]['Staked_amount_Long'][i]+= vault[pair]['notional'][i]
                        amm[pair]['net_exposure'][i] -= vault[pair]['notional'][i]           
                        amm[pair]['Ratio'][i]=amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                        amm[pair]['Quote_initial'][i]= apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]     
                        #average the price 
                        #new average price = (old average price * old position + new position * new price) / (total position)
                        vault[pair]['avg_price'][i]=(vault[pair]['avg_price'][i-1]*vault[pair]['position'][i-1]+vault[pair]['notional'][i]*amm[pair]['Quote_initial'][i])/(vault[pair]['position'][i-1]+vault[pair]['notional'][i])
                        vault[pair]['position'][i]+=vault[pair]['notional'][i]
                        vault[pair]['collateral'][i] += vault[pair]['notional'][i]/3
                        vault[pair]['trading_fee_in'][i] = amm[pair]['Quote_initial'][i]*0.01*0.01*vault[pair]['notional'][i]
                        vault[pair]['days_elapsed'][i] = vault[pair]['days_elapsed'][i-1]+1
                        vault[pair]['Unrealized_PnL'][i] = calcUnrealized_perp(vault[pair],i)
                        #update the cash reserves
                        vault_summary['Cash_reserves'][i]-=vault[pair]['notional'][i]/3 #collateral used 
                        vault_summary['USDC_Balance'][i]-=vault[pair]['notional'][i]/3 #collateral used 
                        price_before = (apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
                        amm[pair]['slippage'][i]=np.nanmean([amm[pair]['slippage'][i],abs(price_before - amm[pair]['Quote_initial'][i])/price_before])
                        #update the trading income into AMM 
                        vault[pair]['trading_fee_in'][i]=vault[pair]['notional'][i]*amm[pair]['Quote_initial'][i]*0.01*0.01
                        """updatee revenue, USDC_balance and staking amount of AMM, TL and TS for the next trader"""
                        #AMM only gets 75% of trading fee_in
                        amm[pair]['revenue'][i]+=vault[pair]['trading_fee_in'][i]*0.75
                        amm[pair]['USDC_Balance'][i]+=vault[pair]['trading_fee_in'][i]*0.75
                        amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['revenue'][i] \
                        #there is no realized pnl in day 1 
                        amm[pair]['Staked_amount_Long'][i]+=vault[pair]['trading_fee_in'][i]*0.75*(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
                        amm[pair]['Staked_amount_Short'][i]+=vault[pair]['trading_fee_in'][i]*0.75*1/(1+amm[pair]['Ratio'][i])
                        amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                        amm[pair]['Quote_initial'][i]=(apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
                        #update vault volume from vault daily rebalance 
                        vault[pair]['cumulative_Trading_vol'][i] += vault[pair]['notional'][i] #only accumulate every 1 day, no need to add from prev days
                        vault[pair]['Rebalance_count'][i]+=1
                        amm[pair]['cumulative_Trading_Vol_rebased_agg'][i] +=vault[pair]['cumulative_Trading_vol'][i]
                        #update vault_summary 
                        vault_summary['Cash_reserves'][i] -= vault[pair]['trading_fee_in'][i] #charge the trading fee when partially closing the position 
                        vault_summary['USDC_Balance'][i] -=vault[pair]['trading_fee_in'][i]
                        #Insurance pool gets 5% of trading fee_in and 20% goes to governence 
                        insurance['trading_fee'][i]+=vault[pair]['trading_fee_in'][i]*0.25
                        amm[pair]['apy_history'][i]=apy_history[pair][i]        
                        amm[pair]['apy_history_trailing'][i]=apy_history_trailing[pair][i]
                    #close / reduce the position 
                    elif vault[pair]['Rebal_size'][i]<0:
                        #close down some position 
                        vault[pair]['notional'][i] = abs(vault[pair]['Rebal_size'][i])
                        if vault[pair]['Rebal_size'][i] > vault[pair]['position'][i]: #cannot close more than you have on teh existing open position 
                            partial = 1
                            vault[pair]['days_elapsed'][i] = 0
                        else:
                            partial = vault[pair]['notional'][i] / vault[pair]['position'][i]
                            vault[pair]['days_elapsed'][i] = vault[pair]['days_elapsed'][i-1]+1
                        #default for closing to cut loss or take profit 
                        vault[pair]['trading_fee_in'][i]=0#since we decide to close some position
                        vault[pair]['Rebalance_count'][i]+=1
                        vault[pair]['notional'][i] = vault[pair]['position'][i]*partial #close the remaining position as of today 
                        vault_summary['Cash_reserves'][i] += vault[pair]['collateral'][i]*partial #return the collateral on partially closed position 
                        vault_summary['USDC_Balance'][i] += vault[pair]['collateral'][i]*partial 
                        vault[pair]['collateral'][i] = vault[pair]['collateral'][i]* (1-partial) #inhereted already if not adding additional collateral
                        vault[pair]['position'][i] = vault[pair]['position'][i-1]-vault[pair]['notional'][i]
                        #When long positino is liquidated/closed, Staked_unt_Long will decrease                       
                        amm[pair]['Staked_amount_Long'][i]-=vault[pair]['notional'][i]
                        #AMM net exposure is less hort 
                        amm[pair]['net_exposure'][i] += vault[pair]['notional'][i]
                        #update the new ratio for pricing and slippage 
                        price_before = (apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
                        amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                        amm[pair]['Quote_initial'][i]= apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                        amm[pair]['apy_history'][i]=apy_history[pair][i]
                        amm[pair]['apy_history_trailing'][i]=apy_history_trailing[pair][i]
                        amm[pair]['slippage'][i]=np.nanmean([amm[pair]['slippage'][i],abs(price_before - amm[pair]['Quote_initial'][i])/price_before])                
                        #calculate Realized PnL on the closed position 
                        if vault[pair]['side'][i-1]==1:
                            vault[pair]['realized_trading_PnL'][i]=0.0
                            vault[pair]['realized_trading_PnL'][i]=-1*(vault[pair]['avg_price'][i]*0.01-amm[pair]['Quote_initial'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)*vault[pair]['notional'][i]
                            #trader receive floating(receive funding PnL)
                            date = i
                            vault[pair]['realized_funding_PnL'][i]=0.0
                            for k in range(1,int(vault[pair]['days_elapsed'][i])+1):
                                vault[pair]['realized_funding_PnL'][i]+=1*(apy_history[pair][date-1]-vault[pair]['avg_price'][date-1])*1/30*0.01*vault[pair]['notional'][i]
                                date = date -1 
                        #aggregate unrealized PnL    
                        vault[pair]['Realized_PnL'][i]=(vault[pair]['realized_trading_PnL'][i]+vault[pair]['realized_funding_PnL'][i])    
                        if vault[pair]['Realized_PnL'][i]<0:
                            insurance['profit'][i] -= (vault[pair]['Realized_PnL'][i]*0.10)
                            aggregate_Realized_PnL[pair] -=(vault[pair]['Realized_PnL'][i]*0.9)
                            amm[pair]['Realized_PnL'][i]-= vault[pair]['Realized_PnL'][i]*0.9
                            pre_usdc_value = amm[pair]['USDC_Balance'][i]
                            amm[pair]['USDC_Balance'][i]-= vault[pair]['Realized_PnL'][i]*0.9
                            amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['USDC_Balance'][i]
                            amm[pair]['Staked_amount_Long'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
                            amm[pair]['Staked_amount_Short'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *1/(1+amm[pair]['Ratio'][i])
                            amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                            amm[pair]['Quote_initial'][i]=apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                            #vault[pair]['actual_received'][i]= vault[pair]['Realized_PnL'][i] 
                        else: # if trader make money, then AMM take all the loss 
                            aggregate_Realized_PnL[pair] -= vault[pair]['Realized_PnL'][i]
                            amm[pair]['Realized_PnL'][i]-= vault[pair]['Realized_PnL'][i]
                            if vault[pair]['Realized_PnL'][i]>amm[pair]['USDC_Balance'][i]:
                                amm[pair]['Staked_amount_LP_token'][i] -= vault[pair]['Realized_PnL'][i]/uniswap_market['LP_Token_Price'][i] 
                                insufficient_trader[pair]+=1
                                amm[pair]['Staked_amount'][i] =virtual_liquidity+ amm[pair]['Staked_amount_LP_token'][i] * uniswap_market['LP_Token_Price'][i]+amm[pair]['USDC_Balance'][i] 
                                amm[pair]['Staked_amount_Long'][i] -= vault[pair]['Realized_PnL'][i]*amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i])
                                amm[pair]['Staked_amount_Short'][i] -= vault[pair]['Realized_PnL'][i]*1/(1+amm[pair]['Ratio'][i])  
                            elif vault[pair]['Realized_PnL'][i]<=amm[pair]['USDC_Balance'][i]:
                                pre_usdc_value = amm[pair]['USDC_Balance'][i]
                                amm[pair]['USDC_Balance'][i] -= vault[pair]['Realized_PnL'][i]
                                amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['USDC_Balance'][i]
                                amm[pair]['Staked_amount_Long'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
                                amm[pair]['Staked_amount_Short'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *1/(1+amm[pair]['Ratio'][i])
                                amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                                amm[pair]['Quote_initial'][i]=apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                        #If exit, charge the trading_fee_out
                        vault[pair]['exit_level'][i]=amm[pair]['Quote_initial'][i]
                        vault[pair]['trading_fee_out'][i]=vault[pair]['exit_level'][i]*0.01*vault[pair]['notional'][i]*0.01
                        #vault[pair]['actual_received'][i]=vault[pair]['Realized_PnL'][i]              
                        #Aggregate the trading_fee_out to AMM and Insurance
                        aggregate_Revenue[pair] += vault[pair]['trading_fee_out'][i]*0.75
                        amm[pair]['revenue'][i] += vault[pair]['trading_fee_out'][i]*0.75
                        pre_usdc_value = amm[pair]['USDC_Balance'][i]
                        amm[pair]['USDC_Balance'][i] += vault[pair]['trading_fee_out'][i]*0.75
                        amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['USDC_Balance'][i]
                        amm[pair]['Staked_amount_Long'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
                        amm[pair]['Staked_amount_Short'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *1/(1+amm[pair]['Ratio'][i])
                        amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                        amm[pair]['Quote_initial'][i]=apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                        insurance['trading_fee'][i]+=(vault[pair]['trading_fee_out'][i]*0.25)
                        #update vault_summary 
                        vault_summary['Cash_reserves'][i] -= vault[pair]['trading_fee_out'][i] #charge the trading fee when partially closing the position 
                        vault_summary['USDC_Balance'][i] -=vault[pair]['trading_fee_out'][i]
                        vault_summary['Cash_reserves'][i] += vault[pair]['Realized_PnL'][i] #charge or receive the realized pnl from partially closing the position 
                        vault_summary['USDC_Balance'][i] += vault[pair]['Realized_PnL'][i]
                        #update the vault volume and amm volume from the vaul daily rebalance 
                        vault[pair]['cumulative_Trading_vol'][i] += vault[pair]['notional'][i] #only accumulate every 1 day, no need to add from prev days
                        vault[pair]['Rebalance_count'][i]+=1
                        amm[pair]['cumulative_Trading_Vol_rebased_agg'][i] +=vault[pair]['cumulative_Trading_vol'][i]
                    
    def updateVault_summary(i): #self = vault_summary
        vault_summary['Realized_PnL'][i] = vault['aave']['Realized_PnL'][i]+vault['binance']['Realized_PnL'][i]+vault['compound']['Realized_PnL'][i]+vault['dydx']['Realized_PnL'][i]+vault['ftx']['Realized_PnL'][i]
        vault_summary['Unrealized_PnL'][i] = vault['aave']['Unrealized_PnL'][i]+vault['binance']['Unrealized_PnL'][i]+vault['compound']['Unrealized_PnL'][i]+vault['dydx']['Unrealized_PnL'][i]+vault['ftx']['Unrealized_PnL'][i]
        vault_summary['Rebalance_count'][i] = vault['aave']['Rebalance_count'][i]+vault['binance']['Rebalance_count'][i]+vault['compound']['Rebalance_count'][i]+vault['dydx']['Rebalance_count'][i]+vault['ftx']['Rebalance_count'][i]
        for pair in currencies:
            vault_summary['Utility_capital%'][i] = vault[pair]['Utility_capital%'][i]/5
        vault_summary['collateral'][i] = vault['aave']['collateral'][i]+vault['binance']['collateral'][i]+vault['compound']['collateral'][i]+vault['dydx']['collateral'][i]+vault['ftx']['collateral'][i]
        #reflect the total day trading volume of the vault over 5 markets 
        vault_summary['notional'][i] = vault['aave']['notional'][i]+vault['binance']['notional'][i]+vault['compound']['notional'][i]+vault['dydx']['notional'][i]+vault['ftx']['notional'][i]
        vault_summary['position'][i] = vault['aave']['position'][i]+vault['binance']['position'][i]+vault['compound']['position'][i]+vault['dydx']['position'][i]+vault['ftx']['position'][i]
        vault_summary['trading_fee_in'][i] = vault['aave']['trading_fee_in'][i]+vault['binance']['trading_fee_in'][i]+vault['compound']['trading_fee_in'][i]+vault['dydx']['trading_fee_in'][i]+vault['ftx']['trading_fee_in'][i]
        vault_summary['trading_fee_out'][i] = vault['aave']['trading_fee_out'][i]+vault['binance']['trading_fee_out'][i]+vault['compound']['trading_fee_out'][i]+vault['dydx']['trading_fee_out'][i]+vault['ftx']['trading_fee_out'][i]
        vault_summary['cumulative_Trading_vol'][i] = vault['aave']['cumulative_Trading_vol'][i]+vault['binance']['cumulative_Trading_vol'][i]+vault['compound']['cumulative_Trading_vol'][i]+vault['dydx']['cumulative_Trading_vol'][i]+vault['ftx']['cumulative_Trading_vol'][i]   
    
    def lpPrice_USDC_exUnrealized(i): #self = vault[pair]     
        #lpPrice = (collateral+realized_pnl+cash_reserves)/(total supply)
        #total_supply is minted and increased when someone deposit and burnt and decreasd when someone withdraw 
        vault_summary['lpPrice_exUnrealized'][i] = (vault_summary['collateral'][i]+vault_summary['Cash_reserves'][i]) / vault_summary['total_supply'][i] #total supply, cash reserves and USDC balances are the same for all markets at the same time 
    
    def lpPrice_USDC_inUnrealized(i):
        vault_summary['lpPrice_inUnrealized'][i] = (vault_summary['collateral'][i]+vault[pair]['Unrealized_PnL'][i]\
                                              +vault_summary['Cash_reserves'][i])/vault_summary['total_supply'][i]
   
    def lpPrice_STRP(i):
        vault_summary['lpPrice_STRP'][i] = vault_summary['STRP_reward'][i]/vault_summary['total_supply'][i]
    
    def deposit(i,amount,method):
        #use lpPrice to decide the LP amount to be received when minting based on USDC amount deposited
        if i>0:
            updateVault_summary(i)
            lpPrice_USDC_exUnrealized(i)
            lpPrice_USDC_inUnrealized(i)
        if method == 'lpPrice_exUnrealized':   
            vault_summary['total_supply'][i] += amount/vault_summary['lpPrice_exUnrealized'][i]
            vault_summary['Cash_reserves'][i] += amount 
            vault_summary['USDC_Balance'][i] += amount 
            investors[j]['amount_USDC_in'][i] = amount 
            investors[j]['entry_lpPrice_exUnrealized'][i] = vault_summary['lpPrice_exUnrealized'][i]
            investors[j]['entry_lpPrice_STRP'][i] = vault_summary['lpPrice_STRP'][i]
            investors[j]['amount_LP'][i] = amount/vault_summary['lpPrice_exUnrealized'][i]
            updateVault_summary(i)
            lpPrice_USDC_exUnrealized(i)
            lpPrice_USDC_inUnrealized(i)

        elif method == 'lpPrice_inUnrealized':
            vault_summary['total_supply'][i] += amount/vault_summary['lpPrice_inUnrealized'][i]
            vault_summary['Cash_reserves'][i] += amount 
            vault_summary['USDC_Balance'][i] +=amount  
            updateVault_summary(i)
            lpPrice_USDC_exUnrealized(i)
            lpPrice_USDC_inUnrealized(i)
            investors[j]['amount_USDC_in'][i] = amount 
            investors[j]['entry_lpPrice_exUnrealized'][i] = vault_summary['lpPrice_inUnrealized'][i]
            investors[j]['entry_lpPrice_STRP'][i] = vault_summary['lpPrice_STRP'][i]
            investors[j]['amount_LP'][i] = amount/vault_summary['lpPrice_inUnrealized'][i]
     
    def withdraw(i,method):
        #use lpPrice to decide the USDC amount to be returned when burning based on LP returned to vault
        #check if any position need to be closed
        #USDC balance of the vault include: 
        #(1) usdc charged from withdrawal fee used to pay gas fee
        #(2) Realized pnl which is pending to be paid out to the traders 
        #(3) cash reserves which is used to add collateral or put on new trades, we should not used realized pnl to add new positions
        #(4) collateral which is used cash for open positions 
        """Should Realized PnL be considered part of cash reserves - can Realized profit used to add collateral or position - Yes"""
        ratio = investors[j]['amount_LP'][i]/vault_summary['total_supply'][i]
        for pair in currencies: 
            #if there is no active position, then no need to close any position before withdraw, just need to update realized pnl and price of the vault, and then 
            if vault[pair]['position'][i] == 0.0:
                pass
            elif vault[pair]['position'][i] !=0.0:
                old_notional = vault[pair]['notional'][i]
                vault[pair]['notional'][i] += vault[pair]['position'][i]* ratio #add more notional of "closing"
                old_collateral = vault[pair]['collateral'][i]
                vault[pair]['collateral'][i] -= vault[pair]['collateral'][i]*ratio  #reducing the collateral
                vault[pair]['position'][i] -= vault[pair]['position'][i]*ratio 
                if vault[pair]['side'][i]==-1:#if trader is short
                    #When short position is liquidated/closed, Staked_amount_Short will decrease 
                    amm[pair]['Staked_amount_Short'][i] -= (vault[pair]['notional'][i]-old_notional)
                    #AMM net exposure is less long, so minus positive number
                    amm[pair]['net_exposure'][i] -= (vault[pair]['notional'][i]-old_notional)
                if vault[pair]['side'][i]==1:
                    #When long positino is liquidated/closed, Staked_unt_Long will decrease                       
                    amm[pair]['Staked_amount_Long'][i]-= (vault[pair]['notional'][i]-old_notional)
                    #AMM net exposure is less hort 
                    amm[pair]['net_exposure'][i] += (vault[pair]['notional'][i]-old_notional)
                vault_summary['Cash_reserves'][i] += old_collateral*ratio #return the collateral on partially closed position 
                vault_summary['USDC_Balance'][i] += old_collateral*ratio
       
                #update the new ratio for pricing and slippage 
                price_before = (apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
                amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                amm[pair]['Quote_initial'][i]= apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                amm[pair]['apy_history'][i]=apy_history[pair][i]
                amm[pair]['apy_history_trailing'][i]=apy_history_trailing[pair][i]
                amm[pair]['slippage'][i]=np.nanmean([amm[pair]['slippage'][i],abs(price_before - amm[pair]['Quote_initial'][i])/price_before])
                #update vault volume from withdrawal activity 
                vault[pair]['cumulative_Trading_vol'][i] += (vault[pair]['notional'][i]-old_notional) #add on top the rebalance volume
                vault[pair]['Rebalance_count'][i]+=1
                amm[pair]['cumulative_Trading_Vol_rebased_agg'][i]+= (vault[pair]['notional'][i]-old_notional) 
                #calculate Realized PnL on the closed position when withdrawing (add on top of the existing realized pnl on the balance)
                old_realized_funding_pnl = vault[pair]['realized_funding_PnL'][i]
                if vault[pair]['avg_price'][i-1]!=0.0:
                    #because this trader has an open position, then elapsed day +1 from previous date
                    if vault[pair]['side'][i]==-1:
                        vault[pair]['realized_trading_PnL'][i]=1*(vault[pair]['avg_price'][i]*0.01-amm[pair]['Quote_initial'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)*(vault[pair]['notional'][i]-old_notional)
                        date = i
                        vault[pair]['realized_funding_PnL'][i]=0
                        for k in range(1,int(vault[pair]['days_elapsed'][i])+1):   
                            #keep adding payments
                            vault[pair]['realized_funding_PnL'][i]=-1*(apy_history[pair][date-1]-vault[pair]['avg_price'][date-1])*1/30*0.01*(vault[pair]['notional'][i]-old_notional)
                            date = date -1 
                    elif vault[pair]['side'][i]==1:
                       vault[pair]['realized_trading_PnL'][i]=-1*(vault[pair]['avg_price'][i]*0.01-amm[pair]['Quote_initial'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)*(vault[pair]['notional'][i]-old_notional)
                       date = i
                       vault[pair]['realized_funding_PnL'][i]=0
                       for k in range(1,int(vault[pair]['days_elapsed'][i])+1):
                           vault[pair]['realized_funding_PnL'][i]+=1*(apy_history[pair][date-1]-vault[pair]['avg_price'][date-1])*1/30*0.01*(vault[pair]['notional'][i]-old_notional)
                           date = date -1 
                additional_realized_pnl = (vault[pair]['realized_trading_PnL'][i]+vault[pair]['realized_funding_PnL'][i])   
                vault[pair]['Realized_PnL'][i] += additional_realized_pnl   
                #calculate Unrealized PnL again on remaining open position 
                #some of the unrealized pnl are paid out after closing the position 
                vault[pair]['Unrealized_PnL'][i] = calcUnrealized_perp(vault[pair],i) - vault[pair]['realized_funding_PnL'][i]- old_realized_funding_pnl
                if vault[pair]['position'][i] ==0:
                    vault[pair]['days_elapsed'][i]=0# set the elapsed days to 0 if the position has been closed, otherwise will be +1 if position is not closed 
                else:
                    pass 
                if additional_realized_pnl <0:
                    insurance['profit'][i] -= additional_realized_pnl*0.10
                    aggregate_Realized_PnL[pair] -= additional_realized_pnl*0.9
                    amm[pair]['Realized_PnL'][i]-= additional_realized_pnl*0.9
                    pre_usdc_value = amm[pair]['USDC_Balance'][i]
                    amm[pair]['USDC_Balance'][i]-= additional_realized_pnl*0.9
                    amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['USDC_Balance'][i]
                    amm[pair]['Staked_amount_Long'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
                    amm[pair]['Staked_amount_Short'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *1/(1+amm[pair]['Ratio'][i])
                    amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                    amm[pair]['Quote_initial'][i]=apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                    #vault[pair]['actual_received'][i]= vault[pair]['Realized_PnL'][i] 
                elif additional_realized_pnl > 0 : # if trader make money, then AMM take all the loss 
                    aggregate_Realized_PnL[pair] -= additional_realized_pnl
                    amm[pair]['Realized_PnL'][i]-= additional_realized_pnl
                    if additional_realized_pnl>amm[pair]['USDC_Balance'][i]:
                        amm[pair]['Staked_amount_LP_token'][i] -= additional_realized_pnl/uniswap_market['LP_Token_Price'][i] 
                        insufficient_trader[pair]+=1
                        amm[pair]['Staked_amount'][i] =virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i] * uniswap_market['LP_Token_Price'][i]+amm[pair]['USDC_Balance'][i] 
                        amm[pair]['Staked_amount_Long'][i] -= additional_realized_pnl*amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i])
                        amm[pair]['Staked_amount_Short'][i] -= additional_realized_pnl*1/(1+amm[pair]['Ratio'][i])  
                        pre_usdc_value = amm[pair]['USDC_Balance'][i]
                        amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['USDC_Balance'][i]
                        amm[pair]['Staked_amount_Long'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
                        amm[pair]['Staked_amount_Short'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *1/(1+amm[pair]['Ratio'][i])
                        amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                        amm[pair]['Quote_initial'][i]=apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                    elif additional_realized_pnl<=amm[pair]['USDC_Balance'][i]:
                        pre_usdc_value = amm[pair]['USDC_Balance'][i]
                        amm[pair]['USDC_Balance'][i] -= additional_realized_pnl
                        amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['USDC_Balance'][i]
                        amm[pair]['Staked_amount_Long'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
                        amm[pair]['Staked_amount_Short'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *1/(1+amm[pair]['Ratio'][i])
                        amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                        amm[pair]['Quote_initial'][i]=apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                #If exit, charge the trading_fee_out
                vault[pair]['exit_level'][i]=amm[pair]['Quote_initial'][i]
                vault[pair]['trading_fee_out'][i]+=vault[pair]['exit_level'][i]*0.01*(vault[pair]['notional'][i]-old_notional)*0.01
                #vault[pair]['actual_received'][i]=vault[pair]['Realized_PnL'][i]              
                #Aggregate the trading_fee_out to AMM and Insurance
                aggregate_Revenue[pair] += vault[pair]['trading_fee_out'][i]*0.75
                amm[pair]['revenue'][i] += vault[pair]['trading_fee_out'][i]*0.75
                pre_usdc_value = amm[pair]['USDC_Balance'][i]
                amm[pair]['USDC_Balance'][i] += vault[pair]['trading_fee_out'][i]*0.75
                amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['USDC_Balance'][i]
                amm[pair]['Staked_amount_Long'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
                amm[pair]['Staked_amount_Short'][i] += (amm[pair]['USDC_Balance'][i]-pre_usdc_value) *1/(1+amm[pair]['Ratio'][i])
                amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                amm[pair]['Quote_initial'][i]=apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                insurance['trading_fee'][i]+=(vault[pair]['trading_fee_out'][i]*0.25)
                #update vault_summary and vault
                #charge the trading fee when partially closing the position 
                vault_summary['Cash_reserves'][i] -= vault[pair]['exit_level'][i]*0.01*(vault[pair]['notional'][i]-old_notional)*0.01 
                vault_summary['USDC_Balance'][i] -=vault[pair]['exit_level'][i]*0.01*(vault[pair]['notional'][i]-old_notional)*0.01
                vault_summary['Cash_reserves'][i] += additional_realized_pnl   
                vault_summary['USDC_Balance'][i] += additional_realized_pnl   
                #update the LP price of the vault  
                updateVault_summary(i)
                lpPrice_USDC_exUnrealized(i)
                lpPrice_USDC_inUnrealized(i)

        if method == 'lpPrice_inUnrealized':
            vault_summary['total_supply'][i] -= investors[j]['amount_LP'][i]           
            #assume the cost is just 2% on the USDC notional 
            #acctual cost will be decided after checking frequency of rebalance and per trade estimated cost is 2.5USDC for gas fee of opening and closing positions
            investors[j]['amount_USDC_out'][i] = (1-withdraw_fee)* investors[j]['amount_LP'][i]*vault_summary['lpPrice_inUnrealized'][i] #this price is before total_supply is updated 
            investors[j]['withdraw_fee'][i] = withdraw_fee * investors[j]['amount_LP'][i]*vault_summary['lpPrice_inUnrealized'][i]
            investors[j]['exit_lpPrice_inUnrealized'][i] = vault_summary['lpPrice_USDC_inUnrealized'][i]
            vault_summary['Cash_reserves'][i] -=investors[j]['amount_USDC_out'][i]
            vault_summary['USDC_Balance'][i] -= investors[j]['amount_USDC_out'][i]
            vault_summary['USDC_Balance'][i] += investors[j]['withdraw_fee'][i]
            investors[j]['amount_LP'][i] = 0 #set to zero 
            updateVault_summary(i)
            #update the LP price 
            lpPrice_USDC_inUnrealized(i)
            lpPrice_USDC_exUnrealized(i)
            lpPrice_STRP(i)
                
        elif method == 'lpPrice_exUnrealized':
            vault_summary['total_supply'][i] -= investors[j]['amount_LP'][i]
            #assume the cost is just 2% on the USDC notional 
            #acctual cost will be decided after checking frequency of rebalance and per trade estimated cost is 2.5USDC for gas fee of opening and closing positions
            investors[j]['amount_USDC_out'][i] = (1-withdraw_fee)* investors[j]['amount_LP'][i]*vault_summary['lpPrice_exUnrealized'][i]
            investors[j]['withdrawal_fee'][i] = withdraw_fee * investors[j]['amount_LP'][i]*vault_summary['lpPrice_exUnrealized'][i]
            investors[j]['exit_lpPrice_exUnrealized'][i] = vault_summary['lpPrice_exUnrealized'][i]
            vault_summary['Cash_reserves'][i] -= investors[j]['amount_USDC_out'][i]
            vault_summary['USDC_Balance'][i] -= investors[j]['amount_USDC_out'][i]
            vault_summary['USDC_Balance'][i] += investors[j]['withdrawal_fee'][i]
            investors[j]['amount_LP'][i] = 0 #set to zero 
            investors[j]['exit_lpPrice_STRP'][i] = vault_summary['lpPrice_STRP'][i]
            updateVault_summary(i)
            lpPrice_USDC_exUnrealized(i)
            lpPrice_USDC_inUnrealized(i)
        
        #balance_STRP in vault increase from Time_0 to Time_t 
        #vault STRP price increased from B_0/totalSupply0 (nothing belons to me) to B_t/totalSupply_t (I have a portion)
        #Therefore the STRP profit is amount_LP * (B_t/totalSupply_t - B_0/totalSupply_0)
        investors[j]['profit_STRP'][i] = investors[j]['amount_LP'][i-1] * (investors[j]['exit_lpPrice_STRP'][i]-investors[j]['entry_lpPrice_STRP'][i])
        investors[j]['profit_USDC'][i] = investors[j]['amount_USDC_out'][i]-investors[j]['amount_USDC_in'][i-1]
        investors[j]['total_profit_USDC'][i] = investors[j]['profit_STRP'][i] * uniswap_market['STRP_Price'][i] + investors[j]['profit_USDC'][i]
        vault_summary['STRP_reward'][i] -= investors[j]['profit_STRP'][i]

    #day 0 start
    uniswap_market = pd.DataFrame(0.0,columns = ['STRP_Price','STRP_Inventory','USDC_Inventory','LP_Token_amount','LP_Token_Price'],index=apy_history.index)
    uniswap_market['STRP_Price'][0]=1.0
    uniswap_market['STRP_Inventory'][0]=math.sqrt(1000000000000/uniswap_market['STRP_Price'][0])
    uniswap_market['USDC_Inventory'][0]=1000000000000/uniswap_market['STRP_Inventory'][0]
    uniswap_market['LP_Token_Price'][0]=(uniswap_market['USDC_Inventory'][0]+uniswap_market['STRP_Price'][0]*uniswap_market['STRP_Inventory'][0])/\
            (uniswap_market['USDC_Inventory'][0]+uniswap_market['STRP_Price'][0]*uniswap_market['STRP_Inventory'][0])
    uniswap_market['LP_Token_amount'][0]=(uniswap_market['USDC_Inventory'][0]+uniswap_market['STRP_Price'][0]*uniswap_market['STRP_Inventory'][0])/\
        uniswap_market['LP_Token_Price'][0]
    
    vault_summary = pd.DataFrame(0.0,columns = ['total_supply','vector_sum','countPositiveCarry','averageCarry%','Realized_PnL','Unrealized_PnL','USDC_Balance','Cash_reserves','Rebalance_count',\
                                                'Utility_capital%','collateral','notional','position','trading_fee_in','trading_fee_out',\
                                                    'cumulative_Trading_vol','STRP_reward','lpPrice_STRP','lpPrice_exUnrealized','lpPrice_inUnrealized'],\
                                 index=apy_history.index)

    # Set default values for variables of AMM, Insurance 
    currencies = ['aave','binance','compound','dydx','ftx']
    amm={}
    vault = {}
    rejected = {}
    
    for pair in currencies:
        amm[pair] = pd.DataFrame(columns=['net_exposure','revenue','Realized_PnL','Unrealized_PnL','USDC_Balance','vAMM_staked_amount_LP_token',\
                                          'Staked_amount_LP_token','Staked_amount','Staked_amount_Long','Staked_amount_Short',\
                                                  'Ratio','Quote_initial','apy_history','apy_history_trailing','Liquidated_count','Rejected_count',\
                                                      'insufficient_trader','insufficient_staker','slippage',\
                                                          'Realized_PnL_growth','Unrealized_PnL_growth','revenue_growth','Undistributed_profit_growth',\
                                                              'cumulative_Trading_Vol_rebased_agg','average_trading_period','staking_share','trading_share','profit_staking_over_holding','excess_return','dv01'], index=apy_history.index)
        amm[pair] = amm[pair].fillna(0.0)
        amm[pair]['Staked_amount_LP_token'][0]=uniswap_market['LP_Token_amount'][0]/5 
        #add virtual liquidity 
        amm[pair]['Staked_amount'][0]= virtual_liquidity+amm[pair]['Staked_amount_LP_token'][0]*uniswap_market['LP_Token_Price'][0]
        amm[pair]['Staked_amount_Long'][0]=amm[pair]['Staked_amount'][0]/2
        amm[pair]['Staked_amount_Short'][0]=amm[pair]['Staked_amount'][0]/2
        amm[pair]['Ratio'][0]=1.0
        amm[pair]['slippage'][0]=np.nan
        amm[pair]['average_trading_period'][0]=np.nan
        rejected[pair]=0.0
        ''
        vault[pair] = pd.DataFrame(0.0,columns=['instant_carry%','maxNotional','vector','weight%','targetAllocation','Rebal_size','expected_return','estimated_slippage','expected_cost',\
                                                'expected_net_return','realized_trading_PnL','realized_funding_PnL','Realized_PnL',\
                                                    'trading_PnL','funding_PnL','Unrealized_PnL',\
                                                        'Rebalance_count','Utility_capital%','Decision_eod',\
                                                            'total_supply','collateral','notional','side','avg_price','exit_level','apy_history','position',\
                                                                'trading_fee_in','trading_fee_out','days_elapsed','trading_pnl','funding_pnl',\
                                                                    'cumulative_Trading_vol','STRP_reward'],index=apy_history.index)
    
    insurance = pd.DataFrame(0.0,columns = ['liquidation_fee','profit','trading_fee','revenue','withdrawal','Staked_amount_LP_token','STRP_Price','LP_Token_Price',\
                                            'Staked_amount','Staked_amount_exProfit'],index=apy_history.index)
    insurance['Staked_amount'][0]=1e6 #assume this is treasury money in total of 1m USDC for insurance 
    
    
    # For loop of 50 trader+staker over 387 days and check AMM/Insurance pool's capital change 
    clients = list(range(50))
    investors = {}
    traders = {}
    for name in clients:
        investors[name] = pd.DataFrame(0.0,columns=['entry_lpPrice_exUnrealized','entry_lpPrice_inUnrealized','exit_lpPrice_exUnrealized','exit_lpPrice_inUnrealized',\
                                                  'entry_lpPrice_STRP','exit_lpPrice_STRP','amount_USDC_in','amount_LP','amount_USDC_out',\
                                                      'profit_USDC','profit_STRP','total_profit_USDC','withdrawal_fee'],\
                                     index=apy_history.index)
        traders[name] = pd.DataFrame(0.0,columns=['currency','notional','leverage','collateral','side','entry_lvl','exit_lvl',\
                                                  'trading_fee_in','trading_fee_out','liquidation_fee',\
                                                      'days_elapsed','trading_PnL','funding_PnL','Unrealized_PnL','Realized_PnL','actual_received',\
                                                          'count_trades','average_trading_period',\
                                                              'Trading_Vol_rebased_aave','cumulative_Trading_Vol_rebased_aave',\
                                                                  'Trading_Vol_rebased_binance','cumulative_Trading_Vol_rebased_binance',\
                                                                      'Trading_Vol_rebased_compound','cumulative_Trading_Vol_rebased_compound',\
                                                                          'Trading_Vol_rebased_dydx','cumulative_Trading_Vol_rebased_dydx',\
                                                                              'Trading_Vol_rebased_ftx','cumulative_Trading_Vol_rebased_ftx',\
                                                                                  'reward_trader','reward_staker','total_reward'],\
                                         index=apy_history.index)
        traders[name]['currency']=traders[name]['currency'].astype(str)
            
    
    stakers ={}
    for name in clients:
        stakers[name] = pd.DataFrame(0.0,columns=['currency','STRP_Price','LP_Token_Price',\
                                                  'Staked_LP_Token','Ratio_when_staked','Undistributed_profit','Share_Percentage','Staked_time',\
                                                      'LP_Token_received','USDC_received','reward_staker','restake_amount'],index=apy_history.index)
        stakers[name]['currency']=stakers[name]['currency'].astype(str)
    del(clients)
    
    #day_0 summary
    currencies = ['aave','compound','dydx','binance','ftx']
    i = 0   
    for pair in currencies:
        amm[pair]['Quote_initial'][0]=initial_haircut*apy_history[pair][0]
    vault_summary['lpPrice_STRP'][0]=1.0
    vault_summary['lpPrice_exUnrealized'][0]=1.0
    vault_summary['lpPrice_inUnrealized'][0]=1.0
    
    """staker first"""
    for j in range(0,50):
        pair_staker = random.choice(currencies)
        stakers[j]['currency'][i]=pair_staker
        stakers[j]['STRP_Price'][i]=uniswap_market['STRP_Price'][i]
        stakers[j]['LP_Token_Price'][i]=uniswap_market['LP_Token_Price'][i]
        stakers[j]['Staked_LP_Token'][i]= buySTRP_uniswap(i) #no restake_amount since it is day 0 only adding staking 
        #meaningless data, for check purpose 
        stakers[j]['Ratio_when_staked'][i]=amm[pair_staker]['Ratio'][i]
        """update AMM staked amount after staker j"""
        amm[pair_staker]['Staked_amount_LP_token'][i]+=stakers[j]['Staked_LP_Token'][i]
        pre_staking_amount = amm[pair_staker]['Staked_amount'][i]
        #add virtual liquidity
        amm[pair_staker]['Staked_amount'][i]=virtual_liquidity+amm[pair_staker]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair_staker]['USDC_Balance'][i]
        amm[pair_staker]['Staked_amount_Long'][i]+=(amm[pair_staker]['Staked_amount'][i]-pre_staking_amount)*\
            amm[pair_staker]['Ratio'][i]/(1+amm[pair_staker]['Ratio'][i])
        amm[pair_staker]['Staked_amount_Short'][i]+=(amm[pair_staker]['Staked_amount'][i]-pre_staking_amount)*\
            1/(1+amm[pair_staker]['Ratio'][i])
        amm[pair_staker]['Ratio'][i] = amm[pair_staker]['Staked_amount_Long'][i]/amm[pair_staker]['Staked_amount_Short'][i]
        amm[pair_staker]['Quote_initial'][i]=apy_history[pair_staker][0]*initial_haircut*amm[pair_staker]['Ratio'][i]
    del(pair_staker)
    
    """then 50 investors choose to deposit or withdraw from the trading vault """
    for j in range(0,50):
        #if bool(random.getrandbits(1)):#if choose to deposit or not choose to deposit
            amount = np.random.randint(100,1000)
            deposit(i,amount,method)
    """Vault puts on trades on day0"""
    longOnlyVault(i)    
    print('lp price: '+str(vault_summary['lpPrice_exUnrealized'][i]))
    print('cash balance: '+str(vault_summary['Cash_reserves'][i]))
    #with another 50 random traders 
    for j in range(0,50):
        pair = random.choice(currencies)
        traders[j]['currency'][i]=pair
        traders[j]['collateral'][i]=np.random.randint(10,1000)
        traders[j]['leverage'][i]=random.randint(1,10)
        traders[j]['notional'][i]=traders[j]['collateral'][i]*traders[j]['leverage'][i]
        traders[j]['side'][i]=random.choices(population=[1,-1],
               weights=[entry_ratio(i), (1-entry_ratio(i))])[0]#in nature, people might want to short the rate(receive fixed)
        
        #check if the notional of the trader is allowed 
        if np.sign(traders[j]['side'][i]) > 0: 
            while traders[j]['notional'][i]>0.1*(amm[pair]['Staked_amount'][i]+amm[pair]['net_exposure'][i]+amm[pair]['Unrealized_PnL'][i]):
                rejected[pair] +=1
                traders[j]['collateral'][i]=np.random.randint(10,1000)
                traders[j]['leverage'][i]=random.randint(1,10)
                traders[j]['notional'][i]=traders[j]['collateral'][i]*traders[j]['leverage'][i]
        else: #if short 
            while traders[j]['notional'][i]>0.1*(amm[pair]['Staked_amount'][i]-amm[pair]['net_exposure'][i]+amm[pair]['Unrealized_PnL'][i]):
                rejected[pair] +=1
                traders[j]['collateral'][i]=np.random.randint(10,1000)
                traders[j]['leverage'][i]=random.randint(1,10)
                traders[j]['notional'][i]=traders[j]['collateral'][i]*traders[j]['leverage'][i]
        
        #note the booster is only effective in the same market, so if trader trades in compound, but stake in aave, the cumulative trading volume won't be rebased
        if pair == stakers[j]['currency'][i]:
            traders[j]['Trading_Vol_rebased_'+pair][i]=traders[j]['notional'][i]*(1+stakers[j]['Staked_LP_Token'][i]/amm[pair]['Staked_amount_LP_token'][i])
        else:
            traders[j]['Trading_Vol_rebased_'+pair][i]=traders[j]['notional'][i]
        traders[j]['cumulative_Trading_Vol_rebased_'+pair][i]+=traders[j]['Trading_Vol_rebased_'+pair][i]
        traders[j]['count_trades'][i]+=1
        #update cumulative trading volume and rebased cumulative trading volume for amm
        amm[pair]['cumulative_Trading_Vol_rebased_agg'][i]+=traders[j]['Trading_Vol_rebased_'+pair][i]
    
        """variable entry ratio_set factor of L/S ratio"""
        price_before = (apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
        
        if traders[j]['side'][i] == 1:
            amm[pair]['Staked_amount_Long'][i]+= traders[j]['notional'][i]
            amm[pair]['net_exposure'][i] -= traders[j]['notional'][i]
        elif traders[j]['side'][i] == -1: 
            amm[pair]['Staked_amount_Short'][i]+= traders[j]['notional'][i]
            amm[pair]['net_exposure'][i] += traders[j]['notional'][i]
        
        amm[pair]['Ratio'][i]=amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
        amm[pair]['Quote_initial'][i]= apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
        traders[j]['entry_lvl'][i]=amm[pair]['Quote_initial'][i]
        amm[pair]['slippage'][i]=np.nanmean([amm[pair]['slippage'][i],abs(price_before - amm[pair]['Quote_initial'][i])/price_before])
        
        #update the trading income into AMM 
        traders[j]['trading_fee_in'][i]=traders[j]['notional'][i]*traders[j]['entry_lvl'][i]*0.01*0.01
        
        """update revenue, USDC_balance and staking amount of AMM, TL and TS for the next trader"""
        #AMM only gets 75% of trading fee_in
        amm[pair]['revenue'][i]+=traders[j]['trading_fee_in'][i]*0.75
        amm[pair]['USDC_Balance'][i]+=traders[j]['trading_fee_in'][i]*0.75
        amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair]['revenue'][i] #there is no realized pnl in day 1 
        amm[pair]['Staked_amount_Long'][i]+=traders[j]['trading_fee_in'][i]*0.75*(amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i]))
        amm[pair]['Staked_amount_Short'][i]+=traders[j]['trading_fee_in'][i]*0.75*1/(1+amm[pair]['Ratio'][i])
       
        amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
        amm[pair]['Quote_initial'][i]=(apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
        
        #Insurance pool gets 5% of trading fee_in and 20% goes to governence 
        insurance['trading_fee'][i]+=traders[j]['trading_fee_in'][i]*0.25
        amm[pair]['apy_history'][i]=apy_history[pair][i]        
    del(pair)
    
    """Update Unrealized PnL for each trader at the end of the day0"""
    for j in range(0,50):
        pair = traders[j]['currency'][i]        
        traders[j]['Unrealized_PnL'][i] = traders[j]['side'][i]* traders[j]['notional'][i]*\
            (amm[pair]['Quote_initial'][i]*0.01-traders[j]['entry_lvl'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)
        amm[pair]['Unrealized_PnL'][i] -= traders[j]['Unrealized_PnL'][i]
        pair_staker = stakers[j]['currency'][i]
        stakers[j]['Share_Percentage'][i]=stakers[j]['Staked_LP_Token'][i]/amm[pair_staker]['Staked_amount_LP_token'][i]            
    
    """Update Unrealized PnL for Vault at the end of the day0"""
    for pair in currencies:
        vault[pair]['Unrealized_PnL'][i] = vault[pair]['side'][i] * vault[pair]['notional'][i]*(amm[pair]['Quote_initial'][i]*0.01-vault[pair]['avg_price'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)
        amm[pair]['Unrealized_PnL'][i] -= vault[pair]['Unrealized_PnL'][i]

    updateVault_summary(i)
    vault_summary['STRP_reward'][i] = vault['aave']['STRP_reward'][i]+vault['binance']['STRP_reward'][i]+vault['compound']['STRP_reward'][i]+vault['dydx']['STRP_reward'][i]+vault['ftx']['STRP_reward'][i] 
    lpPrice_USDC_exUnrealized(i)
    lpPrice_USDC_inUnrealized(i)
    
    supply = {}
    for pair in currencies:
        supply[pair]=0.0
    for j in range(0,50):
        pair_staker = stakers[j]['currency'][i]
        supply[pair_staker] += stakers[j]['Staked_LP_Token'][i]
        
    for pair in currencies:
        #update for day after looping over all 50 traders 
        #realized pnl for all trader on day 0 is zero since people just open positions 
        #unrealized funding pnl for all traders on day 0 is also zero, but unrealized trading pnl for all traders are not zero 
        amm[pair]['revenue_growth'][i]=amm[pair]['revenue'][i]-0
        amm[pair]['Unrealized_PnL_growth'][i]= amm[pair]['Unrealized_PnL'][i]-0
        amm[pair]['Undistributed_profit_growth'][i]=amm[pair]['revenue_growth'][i]+ amm[pair]['Realized_PnL_growth'][i]+amm[pair]['Unrealized_PnL_growth'][i]
        amm[pair]['vAMM_staked_amount_LP_token'][i]=amm[pair]['Staked_amount_LP_token'][i]-supply[pair]
        amm[pair]['Rejected_count'][i]+=rejected[pair]
        amm[pair]['excess_return'][i] = (amm[pair]['revenue'][i]+amm[pair]['Realized_PnL'][i]+amm[pair]['Unrealized_PnL'][i])+\
            (amm[pair]['vAMM_staked_amount_LP_token'][i]-400000)*uniswap_market['LP_Token_Price'][i]
    
    """give out rewards to stakers and VAULT at end of day"""
    sum_staking=amm['aave']['Staked_amount_LP_token'][i]+amm['compound']['Staked_amount_LP_token'][i]+amm['binance']['Staked_amount_LP_token'][i]+\
        amm['ftx']['Staked_amount_LP_token'][i]+amm['dydx']['Staked_amount_LP_token'][i]
    sum_trading = amm['aave']['cumulative_Trading_Vol_rebased_agg'][i]+amm['compound']['cumulative_Trading_Vol_rebased_agg'][i]+\
        amm['binance']['cumulative_Trading_Vol_rebased_agg'][i]+amm['ftx']['cumulative_Trading_Vol_rebased_agg'][i]+amm['dydx']['cumulative_Trading_Vol_rebased_agg'][i]
    for pair in currencies:            
        amm[pair]['staking_share'][i]=amm[pair]['Staked_amount_LP_token'][i]/sum_staking
        amm[pair]['trading_share'][i]=amm[pair]['cumulative_Trading_Vol_rebased_agg'][i]/sum_trading
        amm[pair]['Undistributed_profit_growth'][i]=amm[pair]['revenue'][i]+amm[pair]['Realized_PnL_growth'][i]+amm[pair]['Unrealized_PnL_growth'][i]
        #give rewards to vault (the only trader)
        vault[pair]['STRP_reward'][i] = amm[pair]['trading_share'][i]*3651*vault[pair]['cumulative_Trading_vol'][i]/amm[pair]['cumulative_Trading_Vol_rebased_agg'][i]
        
    for j in range(0,50):
        pair_staker = stakers[j]['currency'][i]
        pair = traders[j]['currency'][i]
        stakers[j]['reward_staker'][i] = amm[pair_staker]['staking_share'][i]*3651*stakers[j]['Share_Percentage'][i]
        traders[j]['reward_trader'][i]+=amm[pair]['trading_share'][i]*3651*traders[j]['cumulative_Trading_Vol_rebased_'+pair][i]/amm[pair]['cumulative_Trading_Vol_rebased_agg'][i]
        traders[j]['reward_staker'][i] = stakers[j]['reward_staker'][i]
        traders[j]['total_reward'][i]=traders[j]['reward_trader'][i]+traders[j]['reward_staker'][i]
        stakers[j]['Undistributed_profit'][i]=amm[pair_staker]['Undistributed_profit_growth'][i]*stakers[j]['Share_Percentage'][i]
        #traders can choose to sell their STRP rewards or not (assuming 65% of people will just sell STRP and won't can re-stake to Uniswap LP) 
        #in reality people can also choose to stake in DAO, but since this is out of scope of this simulation, so we assume no one stakes in DAO
        """first liquidity providing - liquidity = sqrt(x0*y0) - min where min = 1000
        else: liquidity = min((x0/reserve0*totalsupply), (y0/reserve1*totalsupply))按照注入的流动性和当前的reserve的占比一致。"""
        # x0/y0 = reserves 0/reserves1
        # y0 = x0 * (reserves 1/ reserves 0) = x0* proportion 
        # proportion is based on the current reserves, before new staking into liquidity pool 
        proportion = uniswap_market['USDC_Inventory'][i]/uniswap_market['STRP_Inventory'][i]
        #1 is to re-stake(20%), 0 is do nothing and leave rewards on balance(60%) and -1 is to sell STRP token and leave (20%)
        STRP_amount_change = traders[j]['total_reward'][i]*random.choices(population=[1,0,-1],weights=[0.2,0.2,0.6])[0]
        USDC_amount_change = STRP_amount_change * proportion #y0=x0 * proportion 
        if  STRP_amount_change>0:#mint LP tokens for the additional staking of USDC+STRP 
            uniswap_market['STRP_Inventory'][i]+=STRP_amount_change
            uniswap_market['USDC_Inventory'][i]+=USDC_amount_change 
            restake_amount = min(STRP_amount_change/uniswap_market['STRP_Inventory'][i]*uniswap_market['LP_Token_amount'][i],\
                                                      USDC_amount_change/uniswap_market['USDC_Inventory'][i]*uniswap_market['LP_Token_amount'][i])
            uniswap_market['LP_Token_amount'][i]+=restake_amount
            uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
                /uniswap_market['LP_Token_amount'][i]   
            #save the restaking amount at the end of day and to be inhereted next day 
            stakers[j]['restake_amount'][i]= restake_amount #minted additional LP tokens
            stakers[j]['reward_staker'][i]=0#set to zero since all minted 
            traders[j]['reward_trader'][i]=0
            traders[j]['reward_staker'][i]=0
            traders[j]['total_reward'][i]=0
        #if = 0, then hold so keep in the format of STRP 
        elif STRP_amount_change<0: #sell STRP on uniswap  
            #uniswap LP will get additional STRP by buying STRP from the seller (STRP inventory increase)
            constant =  uniswap_market['STRP_Inventory'][i]* uniswap_market['USDC_Inventory'][i]#constant k before change 
            uniswap_market['STRP_Inventory'][i]-=STRP_amount_change
            uniswap_market['USDC_Inventory'][i] = constant/uniswap_market['STRP_Inventory'][i]#since it is 50/50
            uniswap_market['STRP_Price'][i]=uniswap_market['USDC_Inventory'][i]/uniswap_market['STRP_Inventory'][i]
            uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
                /uniswap_market['LP_Token_amount'][i]   
            stakers[j]['reward_staker'][i]=0#set to zero since all sold out 
            traders[j]['reward_trader'][i]=0
            traders[j]['reward_staker'][i]=0
            traders[j]['total_reward'][i]=0
            
    insurance['revenue'][i]=insurance['liquidation_fee'][i]+insurance['profit'][i]+insurance['trading_fee'][i]
    insurance['Staked_amount'][i]=insurance['Staked_amount'][i]+insurance['revenue'][i]+insurance['withdrawal'][i]#no withdrawal at day 0 
    
    #from day_2 until day_327 
    #len(apy_history.index)  
    for i in range(1,len(apy_history.index) ):
        print(apy_history.index[i])
        aggregate_Realized_PnL={}
        aggregate_Revenue={}
        aggregate_Unrealized_PnL={}
        liquidated = {}
        insufficient_trader = {}
        insufficient_staker = {}
        
        """update STRP price and LP token price"""
        uniswap_market['STRP_Price'][i]=uniswap_market['STRP_Price'][i-1]*(1+(amm['aave']['Undistributed_profit_growth'][i-1]/amm['aave']['Staked_amount'][i-1]+\
                                     amm['compound']['Undistributed_profit_growth'][i-1]/amm['compound']['Staked_amount'][i-1]+\
                                         amm['binance']['Undistributed_profit_growth'][i-1]/amm['binance']['Staked_amount'][i-1]+\
                                             amm['ftx']['Undistributed_profit_growth'][i-1]/amm['ftx']['Staked_amount'][i-1]+\
                                                 amm['dydx']['Undistributed_profit_growth'][i-1]/amm['dydx']['Staked_amount'][i-1])/5)*(1+btc_history['%percentage'][i])
        #instead of randomly assign buyers and decide the STRP price, we want to create an injective (non-surjective)function (from price to quantity)
        constant = uniswap_market['STRP_Inventory'][i-1]* uniswap_market['USDC_Inventory'][i-1]#constant k before change 
        """STRP_Price * (STRP inventory - STRP bought) = constant / (STRP inventory - bought) * 1"""
        uniswap_market['STRP_Inventory'][i]= math.sqrt( constant / uniswap_market['STRP_Price'][i])
    
        uniswap_market['USDC_Inventory'][i]= constant / uniswap_market['STRP_Inventory'][i]
        uniswap_market['LP_Token_amount'][i]=uniswap_market['LP_Token_amount'][i-1]
        uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
                    /uniswap_market['LP_Token_amount'][i]
        
        for pair in currencies:
            aggregate_Realized_PnL[pair] = 0.0
            aggregate_Revenue[pair] = 0.0 
            aggregate_Unrealized_PnL[pair]=0.0
            liquidated[pair]=0.0
            insufficient_trader[pair]=0.0
            insufficient_staker[pair]=0.0
            
            #inherit the position 
            amm[pair]['Staked_amount_LP_token'][i]=amm[pair]['Staked_amount_LP_token'][i-1]
            amm[pair]['Ratio'][i]=amm[pair]['Ratio'][i-1]
            amm[pair]['revenue'][i]=amm[pair]['revenue'][i-1]
            amm[pair]['Realized_PnL'][i]=amm[pair]['Realized_PnL'][i-1]
            amm[pair]['Unrealized_PnL'][i]=amm[pair]['Unrealized_PnL'][i-1]
            #amm[pair]['Unrealized_PnL'][i]=0
            amm[pair]['USDC_Balance'][i]=amm[pair]['USDC_Balance'][i-1]
            amm[pair]['Staked_amount'][i]=virtual_liquidity+amm[pair]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+ amm[pair]['USDC_Balance'][i]
            amm[pair]['Staked_amount_Long'][i]=amm[pair]['Staked_amount_Long'][i-1]+(amm[pair]['Staked_amount'][i]-amm[pair]['Staked_amount'][i-1])*\
                amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i])
            amm[pair]['Staked_amount_Short'][i]=amm[pair]['Staked_amount_Short'][i-1]+(amm[pair]['Staked_amount'][i]-amm[pair]['Staked_amount'][i-1])*\
                1/(1+amm[pair]['Ratio'][i])
            #since we reset trading volume very 24 hours, and hence we don't need to inherent the amm total trading volume from prev days 
            #amm[pair]['cumulative_Trading_Vol_rebased_agg'][i]=amm[pair]['cumulative_Trading_Vol_rebased_agg'][i-1]
            amm[pair]['average_trading_period'][i]= amm[pair]['average_trading_period'][i-1]
            amm[pair]['net_exposure'][i]=amm[pair]['net_exposure'][i-1]
            amm[pair]['vAMM_staked_amount_LP_token'][i]=amm[pair]['vAMM_staked_amount_LP_token'][i-1]
    
            #update price before any change in order to check the liquidation level 
            amm[pair]['Quote_initial'][i]=(apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
            amm[pair]['apy_history'][i]=apy_history[pair][i]
            amm[pair]['apy_history_trailing'][i]=apy_history_trailing[pair][i]
            
        """stakers first"""
        for j in range(0,50):
            stakers[j]['reward_staker'][i]=stakers[j]['reward_staker'][i-1] #no matter currently staking or not, the reward still belongs to him 
            stakers[j]['restake_amount'][i]=stakers[j]['restake_amount'][i-1] #always inherit the restake_amount first (it is stakers' assets)
                        
            if (stakers[j]['currency'][i-1]!=0.0) & (stakers[j]['Staked_LP_Token'][i-1]!=0.0):    
                stakers[j]['currency'][i]=stakers[j]['currency'][i-1]
                stakers[j]['STRP_Price'][i]=uniswap_market['STRP_Price'][i]
                stakers[j]['LP_Token_Price'][i]=uniswap_market['LP_Token_Price'][i]
                stakers[j]['Staked_LP_Token'][i]=stakers[j]['Staked_LP_Token'][i-1]
                stakers[j]['Undistributed_profit'][i]=stakers[j]['Undistributed_profit'][i-1]
    
                
                pair_staker = stakers[j]['currency'][i-1]
                stakers[j]['Staked_time'][i]=stakers[j]['Staked_time'][i-1]+1
                #Allow stakers to top up capital: 1 means increase, 0 means no change, and -1 means withdrawal, to avoid stake amount goes to 0, only allow the change within range of 10k
                #Make sure staking amount must be no-negative 
                #Realized is cumulative and Unrealized is "current" 
                if checkIPLoss(amm[pair_staker],i)>=0:
                    staked_prob = random.choices(population=[1,0,-1],weights=[0.5,0.3,0.2])[0]
                    amm[pair_staker]['profit_staking_over_holding'][i]=checkIPLoss(amm[pair_staker],i)
                else:   #hold(20%) or redeem(80%) LP tokens if staking profit is not good enough to compensate for IP loss for 10 days 
                    staked_prob = random.choices(population=[1,0,-1],weights=[0.1,0.2,0.7])[0]
                    amm[pair_staker]['profit_staking_over_holding'][i]=checkIPLoss(amm[pair_staker],i)
                
                
                """withdrawal LP Toekn and undistributed pnl growth * days_staked"""
                if staked_prob ==-1: # choose to unstake
                    unstake_percentage =random.choice([0.25,0.5,0.75,1])
                    if stakers[j]['Undistributed_profit'][i]>=0:
                        #vAMM receives the lp token penalty and lock up as permanent treasury staked in this market 
                        #this is different from smart contract and simulation 
                        #in smart contract, lp token received from penalty are recorded as growth to be shared with remaining stakers 
                        #in simulation, we want to see the speed of how fast this vAMM staking liquidity will grow as percentage of total staking liquidity 
                        #vAMM's LP tokens share the USDC growth and decline from trading fee, realized pnl and unrealzied pnl as rights equal with obligations
                        #remaining stakers hence will receive less USDC profit as well as suffer less USDC loss 
                        #this is same as vAMM charges USDC from this unstaking person and immediately use these USDC to buy LP tokens at current price 
                        #unless all stakers unstake at the moment, vAMM won't run into the situation that vAMM cannot pay out the USDC profits to stakers
                        #in smart contract, we directly record lp token growth (together with USDC loss) for remaining stakers, 
                        #and hence we also won't run into the situation that ssmart contract don't have enough USDC to pay stakers' USDCprofits 
                        if stakers[j]['Staked_time'][i]>7:
                            stakers[j]['LP_Token_received'][i] = unstake_percentage*stakers[j]['Staked_LP_Token'][i]
                            burnLP_uniswap(stakers[j], i)
                            
                        else: 
                            stakers[j]['LP_Token_received'][i] = unstake_percentage*stakers[j]['Staked_LP_Token'][i]*\
                                (1-0.02*(7-stakers[j]['Staked_time'][i])/7)
                            burnLP_uniswap(stakers[j], i)
                        
                        stakers[j]['Staked_LP_Token'][i] -= unstake_percentage* stakers[j]['Staked_LP_Token'][i]
                        amm[pair_staker]['Staked_amount_LP_token'][i] -= stakers[j]['LP_Token_received'][i] 
                        """places that need to use the value of prev / after staing amount (instead of LP amount change)
                        - All unstaking (since it has 50% of chance of burning LP tokens and then sell STRP which will lower the STRP Price and LP token price) 
                        - USDC sufficient (then no need to change USDC balance, only USDC balance change need to be reflected in amm long short change since the lp price for staking is already updated) 
                        - USDC insufficient: this steps happens after the unstaking LP tokens (price updated already) and hence can use the new price * amount of LP token change directly 
                        """
                        pre_staking_amount = amm[pair_staker]['Staked_amount'][i]
                        amm[pair_staker]['Staked_amount'][i]= virtual_liquidity+amm[pair_staker]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair_staker]['USDC_Balance'][i]
                        amm[pair_staker]['Staked_amount_Long'][i] +=  (amm[pair_staker]['Staked_amount'][i]-pre_staking_amount) *\
                            amm[pair_staker]['Ratio'][i]/(1+amm[pair_staker]['Ratio'][i])
                        amm[pair_staker]['Staked_amount_Short'][i] +=  (amm[pair_staker]['Staked_amount'][i]-pre_staking_amount) *\
                            1/(1+amm[pair_staker]['Ratio'][i])
                        #check 
                        if (amm[pair_staker]['Staked_amount_Long'][i]<0) or (amm[pair_staker]['Staked_amount_Short'][i]<0):
                            print('WARNING!!!!!!!!!!!!!!!!!!!!')
                            print('point a')
                            sys.exit("Error message")
                        amm[pair_staker]['Ratio'][i] =amm[pair_staker]['Staked_amount_Long'][i]/amm[pair_staker]['Staked_amount_Short'][i]
                        stakers[j]['Ratio_when_staked'][i]=amm[pair_staker]['Ratio'][i]
                        #update the profit received 
                        stakers[j]['USDC_received'][i] = unstake_percentage * stakers[j]['Undistributed_profit'][i]
                        stakers[j]['Undistributed_profit'][i]-=stakers[j]['USDC_received'][i]
                        #in simulation (vAMM mode)
                        #if not sufficient USDC balance to pay stakers, then sell some LP tokens 
                        #all remaining stakers will still be able to get full amount of LP tokens if they unstake after 7 days 
                        #if LP Token is not sufficient to return full amount, we can convert USDC back to LP tokens for this unstaking person 
                        #in smart contract: all remaining stakers will record lp token loss and USDC balance growth 
                        #once the USDC balance growth is paid out, all remaining stakers will record a higher percentage 
                        if amm[pair_staker]['USDC_Balance'][i] >=  stakers[j]['USDC_received'][i]: 
                            amm[pair_staker]['USDC_Balance'][i]-= stakers[j]['USDC_received'][i]
                            amm[pair_staker]['Staked_amount'][i]=virtual_liquidity+ amm[pair_staker]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair_staker]['USDC_Balance'][i]
                            amm[pair_staker]['Staked_amount_Long'][i] -=  stakers[j]['USDC_received'][i]*\
                                amm[pair_staker]['Ratio'][i]/(1+amm[pair_staker]['Ratio'][i])
                            amm[pair_staker]['Staked_amount_Short'][i]-=  stakers[j]['USDC_received'][i]*\
                                1/(1+amm[pair_staker]['Ratio'][i])
                            amm[pair_staker]['Ratio'][i] =amm[pair_staker]['Staked_amount_Long'][i]/amm[pair_staker]['Staked_amount_Short'][i]
                            stakers[j]['Ratio_when_staked'][i]=amm[pair_staker]['Ratio'][i]
                            #check 
                            if (amm[pair_staker]['Staked_amount_Long'][i]<0) or (amm[pair_staker]['Staked_amount_Short'][i]<0):
                                print('WARNING!!!!!!!!!!!!!!!!!!!!')
                                print('point b')
                                sys.exit("Error message")
                        else:
                            #at this moment LP token price is already updated (lower) if unstaker chooses to sell the STRP token (50%)
                            #since amount of LP token change = USDC received / new price (price has been updated already if unstaker chooses to sell STRP tokens which pushes down the STRP price and LP token price)
                            #
                            amm[pair_staker]['Staked_amount_LP_token'][i] -= (stakers[j]['USDC_received'][i]/uniswap_market['LP_Token_Price'][i])
                            insufficient_staker[pair_staker] +=1
                            amm[pair_staker]['Staked_amount'][i]=virtual_liquidity+ amm[pair_staker]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair_staker]['USDC_Balance'][i]
                            amm[pair_staker]['Staked_amount_Long'][i] -=  stakers[j]['USDC_received'][i] *\
                                amm[pair_staker]['Ratio'][i]/(1+amm[pair_staker]['Ratio'][i])
                            amm[pair_staker]['Staked_amount_Short'][i]-=  stakers[j]['USDC_received'][i]*\
                                1/(1+amm[pair_staker]['Ratio'][i])
                            amm[pair_staker]['Ratio'][i] =amm[pair_staker]['Staked_amount_Long'][i]/amm[pair_staker]['Staked_amount_Short'][i]
                            stakers[j]['Ratio_when_staked'][i]=amm[pair_staker]['Ratio'][i]
                            #check 
                            if (amm[pair_staker]['Staked_amount_Long'][i]<0) or (amm[pair_staker]['Staked_amount_Short'][i]<0):
                                print('WARNING!!!!!!!!!!!!!!!!!!!!')
                                print('point c')
                                sys.exit("Error message")
                    else:#if USDC growth is negative, then stakers need to lose LP tokens to pay the undistributed loss when unstaking 
                        if stakers[j]['Staked_time'][i]>7:
                            stakers[j]['LP_Token_received'][i] = unstake_percentage*stakers[j]['Staked_LP_Token'][i]+\
                                    (unstake_percentage * stakers[j]['Undistributed_profit'][i]/uniswap_market['LP_Token_Price'][i])
                            burnLP_uniswap(stakers[j], i)
                        else: 
                            stakers[j]['LP_Token_received'][i] = (unstake_percentage*stakers[j]['Staked_LP_Token'][i]*\
                                                                  (1-0.02*(7-stakers[j]['Staked_time'][i])/7))+\
                                (unstake_percentage * stakers[j]['Undistributed_profit'][i]/uniswap_market['LP_Token_Price'][i])
                            burnLP_uniswap(stakers[j], i)
                        stakers[j]['Staked_LP_Token'][i] -= unstake_percentage * stakers[j]['Staked_LP_Token'][i]
                        stakers[j]['Undistributed_profit'][i]=(1-unstake_percentage)*stakers[j]['Undistributed_profit'][i] 
                        #update AMM LP token balance after the withdrawal fee 
                        #amm gets more LP tokens from penalty(if any) and from undistributed profit of this staker
                        #vAMM offset this staker's liability (USDC balance should grow but it doesn't) to get more LP tokens (minus a negative number as undistributed profit<0)
                        amm[pair_staker]['Staked_amount_LP_token'][i] -= stakers[j]['LP_Token_received'][i]  
                        pre_staking_amount = amm[pair_staker]['Staked_amount'][i]
                        amm[pair_staker]['Staked_amount'][i]=virtual_liquidity+ amm[pair_staker]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]+amm[pair_staker]['USDC_Balance'][i]
                        amm[pair_staker]['Staked_amount_Long'][i] +=  (amm[pair_staker]['Staked_amount'][i]- pre_staking_amount) *\
                            amm[pair_staker]['Ratio'][i]/(1+amm[pair_staker]['Ratio'][i])
                        amm[pair_staker]['Staked_amount_Short'][i]+=   (amm[pair_staker]['Staked_amount'][i]- pre_staking_amount) *\
                            1/(1+amm[pair_staker]['Ratio'][i])
                        amm[pair_staker]['Ratio'][i] =amm[pair_staker]['Staked_amount_Long'][i]/amm[pair_staker]['Staked_amount_Short'][i]
                        stakers[j]['Ratio_when_staked'][i]=amm[pair_staker]['Ratio'][i]
                        #check 
                        if (amm[pair_staker]['Staked_amount_Long'][i]<0) or (amm[pair_staker]['Staked_amount_Short'][i]<0):
                            print('WARNING!!!!!!!!!!!!!!!!!!!!')
                            print('point d')
                            sys.exit("Error message")
                        #update the profit received 
                        #USDC balance should be not lower by adding a negative number (since no USDC balance paid out )
                        #in this case vAMM make a transaction with the unstaking person such taht vAMM loses USDC (wipe out the USDC liability of this staker)
                        #and instead vAMM gets extra LP token at that day's last price 
                        #the difference is that in smart contract, we force all remaining stakers to make this swap, but since we have vAMM in this model, we let vAMM lose the USDC balance for the extra LP tokens 
                        #since nothing paid out to the traders, amm only gets extra lp tokens and 0 dollars back from this staker 
                        #amm[pair_staker]['USDC_Balance'][i]+= unstake_percentage * stakers[j]['Undistributed_profit'][i]
                        
                #choose to carry on the staking position = inherit the last staking position 
                elif staked_prob ==0: 
                    stakers[j]['currency'][i]=stakers[j]['currency'][i-1]
                    stakers[j]['STRP_Price'][i]=uniswap_market['STRP_Price'][i]
                    stakers[j]['LP_Token_Price'][i]=uniswap_market['LP_Token_Price'][i]
                    stakers[j]['Staked_LP_Token'][i]=stakers[j]['Staked_LP_Token'][i-1]
                    stakers[j]['Ratio_when_staked'][i]=stakers[j]['Ratio_when_staked'][i-1]
                    # no need to  add time here since next day, when find out this staking currency !=0.0, will add staking time by one more day 
                    
                #otherwise allow the stakers to top up 
                elif staked_prob == 1:
                    stakers[j]['currency'][i]=stakers[j]['currency'][i-1]
                    stakers[j]['STRP_Price'][i]=uniswap_market['STRP_Price'][i]
                    stakers[j]['LP_Token_Price'][i]=uniswap_market['LP_Token_Price'][i]
                    additional_staking = buySTRP_uniswap(i)+stakers[j]['restake_amount'][i]
                    stakers[j]['Staked_LP_Token'][i]=stakers[j]['Staked_LP_Token'][i-1]+additional_staking
                    stakers[j]['restake_amount'][i]=0 # set to zero since it is re-staked to the exiting market
                    pair_staker = stakers[j]['currency'][i]
                    amm[pair_staker]['Staked_amount_LP_token'][i]+=additional_staking
                    """buying STRP from secondary market will push up STRP price and LP token price hence will need to update long and short from staking amount change
                    since price appreciated for both original staking amount and additional staking amount 
                    """
                    pre_staking_amount = amm[pair_staker]['Staked_amount'][i]
                    amm[pair_staker]['Staked_amount'][i]=virtual_liquidity+amm[pair_staker]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]\
                        +amm[pair_staker]['USDC_Balance'][i]
                    #all need to be updated to new price, additional staking as well as old staking amount 
                    amm[pair_staker]['Staked_amount_Long'][i]+= (amm[pair_staker]['Staked_amount'][i]-pre_staking_amount) *\
                        amm[pair_staker]['Ratio'][i]/(1+amm[pair_staker]['Ratio'][i])
                    amm[pair_staker]['Staked_amount_Short'][i]+= (amm[pair_staker]['Staked_amount'][i]-pre_staking_amount) *\
                        1/(1+amm[pair_staker]['Ratio'][i])
                    amm[pair_staker]['Ratio'][i] =amm[pair_staker]['Staked_amount_Long'][i]/amm[pair_staker]['Staked_amount_Short'][i]
                    stakers[j]['Ratio_when_staked'][i]=amm[pair_staker]['Ratio'][i]
                    #check 
                    if (amm[pair_staker]['Staked_amount_Long'][i]<0) or (amm[pair_staker]['Staked_amount_Short'][i]<0):
                        print('WARNING!!!!!!!!!!!!!!!!!!!!')
                        print('point e')
                        sys.exit("Error message")
                                       
            #if not staked last time, can choose to stake 
            else:   
                pair_staker = random.choice(currencies)
                stakers[j]['currency'][i]=pair_staker
                stakers[j]['Staked_LP_Token'][i] = buySTRP_uniswap(i)+stakers[j]['restake_amount'][i]
                stakers[j]['restake_amount'][i]=0 # set to zero since it is re-staked to the exiting market
                amm[pair_staker]['Staked_amount_LP_token'][i]+=stakers[j]['Staked_LP_Token'][i]
                pre_staking_amount = amm[pair_staker]['Staked_amount'][i]
                amm[pair_staker]['Staked_amount'][i]=virtual_liquidity+amm[pair_staker]['Staked_amount_LP_token'][i]*uniswap_market['LP_Token_Price'][i]\
                    +amm[pair_staker]['USDC_Balance'][i]
                amm[pair_staker]['Staked_amount_Long'][i]+=(amm[pair_staker]['Staked_amount'][i]-pre_staking_amount)*\
                    amm[pair_staker]['Ratio'][i]/(1+amm[pair_staker]['Ratio'][i])
                amm[pair_staker]['Staked_amount_Short'][i]+=(amm[pair_staker]['Staked_amount'][i]-pre_staking_amount)*\
                    1/(1+amm[pair_staker]['Ratio'][i])
                amm[pair_staker]['Ratio'][i] =amm[pair_staker]['Staked_amount_Long'][i]/amm[pair_staker]['Staked_amount_Short'][i]
                stakers[j]['Ratio_when_staked'][i]=amm[pair_staker]['Ratio'][i]
                #check 
                if (amm[pair_staker]['Staked_amount_Long'][i]<0) or (amm[pair_staker]['Staked_amount_Short'][i]<0):
                    print('WARNING!!!!!!!!!!!!!!!!!!!!')
                    print('point f')   
                    sys.exit("Error message")
        
        """then VAULT update""" 
        #before updating the vault, inherent the positions and status of vault_summary from prev day because for loop pair in currencies will cover
        vault_summary['total_supply'][i] = vault_summary['total_supply'][i-1]
        vault_summary['Cash_reserves'][i] = vault_summary['Cash_reserves'][i-1]
        vault_summary['USDC_Balance'][i] = vault_summary['USDC_Balance'][i-1]
        #because we used Realized_PnL.sum() means we don't accumulate the Realized PnL 
        #vault_summary['Realized_PnL'][i] = vault_summary['Realized_PnL'][i-1] 
        #because trading volume resets ever 24 hours, so we don't inheret the cumulative trading volume of vault from prev days 
        vault_summary['STRP_reward'][i] = vault_summary['STRP_reward'][i-1]
        #Run long only strategy
        longOnlyVault(i) 
        #update the LP price before investors can decide to deposit more to withdraw 
        updateVault_summary(i)
        lpPrice_USDC_exUnrealized(i)
        lpPrice_USDC_inUnrealized(i)
        lpPrice_STRP(i)
        print ('after daily rebal, lp price is '+str(vault_summary['lpPrice_exUnrealized'][i]))

        """then investors make decisions about deposit/withdraw from vault"""
        #investors should be able to recieve the STRP reward tokens for the day0
        vault_summary['STRP_reward'][i] = vault['aave']['STRP_reward'][i]+vault['binance']['STRP_reward'][i]+vault['compound']['STRP_reward'][i]+vault['dydx']['STRP_reward'][i]+vault['ftx']['STRP_reward'][i] 
        for j in range(0,50):

            investors[j]['amount_LP'][i] = investors[j]['amount_LP'][i-1] 
            if investors[j]['amount_LP'][i]!=0.0: 
                if bool(random.getrandbits(1)): #if trader choose to withdraw the vault position 
                    withdraw(i,method)
                    print('investor '+str(j)+' after: '+str(investors[j]['exit_lpPrice_exUnrealized'][i]))
                else:
                    #otherwise hold to keep the investment in the vault 
                    investors[j]['entry_lpPrice_exUnrealized'][i] = investors[j]['entry_lpPrice_exUnrealized'][i-1]
                    investors[j]['entry_lpPrice_inUnrealized'][i] = investors[j]['entry_lpPrice_inUnrealized'][i-1]
                    investors[j]['entry_lpPrice_STRP'][i] = investors[j]['entry_lpPrice_STRP'][i-1]
                    investors[j]['amount_USDC_in'][i] = investors[j]['amount_USDC_in'][i-1] 
                    investors[j]['amount_LP'][i] = investors[j]['amount_LP'][i-1] 
                    #if the investor doesn't invest in the past, then randomly decide if this investor wants to         
            else: 
                if bool(random.getrandbits(1)):
                    amount = np.random.randint(100,1000)
                    deposit(i,amount,method)
                else:
                    pass
        """then 50 traders"""
        #if open position exits vs. no open position (indent1)
        #if open position, if liquidated or not liquidated(indent 2)
        #if not liquidated, close it or carry on (indent 3)
        #if no open  position, open or not (indent 2)
        for j in range(0,50):
            #since we reset trading volume for each trader and each market every 24 horus, and hence we don't inherent the trading volumes for each trader any more 
            #for pairs in currencies:
            #    traders[j]['cumulative_Trading_Vol_rebased_'+pairs][i]= traders[j]['cumulative_Trading_Vol_rebased_'+pairs][i-1]
            #First, calculate unrealzied PnL and check if any position need to be liquidated one by one since liquidators will call liquidate function atomically 
            #open position is when last entry level !=0.0 and it is a position with unrealized pnl and hence the position is still open (otherwise unrealized =0 )
            if (traders[j]['entry_lvl'][i-1]!=0.0) & (traders[j]['exit_lvl'][i-1]==0.0):
                pair = traders[j]['currency'][i-1]
                traders[j]['Unrealized_PnL'][i] = calcUnrealized_perp_traders(traders[j],i)
                #allow trader to top up collateral? 1/10 of 10k (original collateral since original notional is 100k)
                #but probability should be lower than 50/50 since the vol of the product is not too high 
                collateral_prob = random.choices(population=[1,0],weights=[0.1,0.9])[0]
                traders[j]['collateral'][i]=traders[j]['collateral'][i-1]\
                    +collateral_prob *np.random.randint(0,1000)
                traders[j]['leverage'][i]=traders[j]['leverage'][i-1]
                traders[j]['days_elapsed'][i]=traders[j]['days_elapsed'][i-1]+1
                """Variable - 5% forced liquidation"""
                # check if trader are liquidated? 
                if (traders[j]['collateral'][i-1]+traders[j]['Unrealized_PnL'][i])<(traders[j]['notional'][i-1]*liquidation_level):
                    liquidated[pair]+=1
                    traders[j]['currency'][i]=traders[j]['currency'][i-1]
                    updateTradingVolume_traders(traders[j],i,j)
                    
                    if traders[j]['side'][i-1]==-1:#if trader is short
                        #When short position is liquidated/closed, Staked_amount_Short will decrease 
                        amm[pair]['Staked_amount_Short'][i] -= traders[j]['notional'][i-1] 
                        #AMM net exposure is less long, so minus positive number
                        amm[pair]['net_exposure'][i] -= traders[j]['notional'][i-1] 
                    if traders[j]['side'][i-1]==1:#trader is long 
                        #When long positino si liquidated/closed, Staked_unt_Long will decrease   
                        amm[pair]['Staked_amount_Long'][i]-=traders[j]['notional'][i-1] 
                        #AMM net exposure is less hort 
                        amm[pair]['net_exposure'][i] += traders[j]['notional'][i-1] 
                    #update the new ratio for pricing 
                    pair = traders[j]['currency'][i-1]
                    amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]        
                    amm[pair]['Quote_initial'][i]=(apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
                    traders[j]['exit_lvl'][i]=amm[pair]['Quote_initial'][i]
                    amm[pair]['apy_history'][i]=apy_history[pair][i]
   
                    #calculate the Unrealized PnL again before liquidating this position (after price changed for the person before)
                    traders[j]['Unrealized_PnL'][i] = calcUnrealized_perp_traders(traders[j],i)
                    if (traders[j]['collateral'][i]+traders[j]['Unrealized_PnL'][i])>=0:#liquidity with positive net equity 
                        traders[j]['liquidation_fee'][i]=(traders[j]['collateral'][i]+traders[j]['Unrealized_PnL'][i])
                        #when liquidation fee is positive, we add on to liquidation fee revenue
                        insurance['liquidation_fee'][i]+=traders[j]['liquidation_fee'][i]
                        # When liquidated, insurance gets 100% of net equity and, and the same time, 
                        # Insurance gets 9.8% of the realized profit (paid from trader to AMM) when liquidated
                        insurance['profit'][i]-=traders[j]['Unrealized_PnL'][i]*0.098 #trader's Unrealized Pnl is ngative, and hence minus negative is to get positive revenue 
                        
                        # Liquidator gets 0.2% of the realized profit (paid from trader to Liquidator) when liquidated
                    else:
                        traders[j]['liquidation_fee'][i]=(traders[j]['collateral'][i]+traders[j]['Unrealized_PnL'][i])#for checking purpose
                        insurance['withdrawal'][i]+=traders[j]['liquidation_fee'][i]
    
                        #insurance still get AMM' positive Realized PnL (trader's Unrealized PnL must be negative, otherwise they would not be liquidated)
                        insurance['profit'][i]-=traders[j]['Unrealized_PnL'][i]*0.098 
                        
                    traders[j]['Realized_PnL'][i]=traders[j]['Unrealized_PnL'][i]
                    traders[j]['actual_received'][i]=-traders[j]['collateral'][i]
                    traders[j]['Unrealized_PnL'][i]=0.0
                    #days_elapsed cleared to 0 if the position is liquidated
                    traders[j]['days_elapsed'][i]=0
                   
                    # Aggregate_Realized_PnL for AMM (they must get all PnL from traders, either from trader or from insurance)
                    # AMM gets only 90% of the realized profit  
                    # liquidator gets 0.2% of the realized profit
                    #insurance gets 9.8% of the realized profit 
                    
                    aggregate_Realized_PnL[pair] -=(traders[j]['Realized_PnL'][i]*0.9) #since trader's realized PnL must negative, then minus negative add to positive AMM PnL
                    amm[pair]['Realized_PnL'][i] -=(traders[j]['Realized_PnL'][i]*0.9) 
                    pre_usdc_value = amm[pair]['USDC_Balance'][i]
                    amm[pair]['USDC_Balance'][i] -=(traders[j]['Realized_PnL'][i]*0.9) 
                    updateAMM(amm[pair],i)
            
                # if not liquidated, let the trader decide if they want to exit the position or not 
                elif(traders[j]['collateral'][i]+traders[j]['Unrealized_PnL'][i])>=(traders[j]['notional'][i-1]*liquidation_level):
                    if bool(random.getrandbits(1)): #if trader choose to close down the position 
                        if traders[j]['side'][i-1]==-1:#if trader is short
                            #When short position is liquidated/closed, Staked_amount_Short will decrease 
                            amm[pair]['Staked_amount_Short'][i] -= traders[j]['notional'][i-1] 
                            #AMM net exposure is less long, so minus positive number
                            amm[pair]['net_exposure'][i] -= traders[j]['notional'][i-1] 
                        if traders[j]['side'][i-1]==1:#trader is long 
                            #When long positino si liquidated/closed, Staked_unt_Long will decrease   
                            amm[pair]['Staked_amount_Long'][i]-=traders[j]['notional'][i-1] 
                            #AMM net exposure is less hort 
                            amm[pair]['net_exposure'][i] += traders[j]['notional'][i-1] 
                        pair_staker = stakers[j]['currency'][i]
                        stakers[j]['Share_Percentage'][i]=stakers[j]['Staked_LP_Token'][i]/amm[pair_staker]['Staked_amount_LP_token'][i]
                        traders[j]['currency'][i]=traders[j]['currency'][i-1]
                        updateTradingVolume_traders(traders[j],i,j)
    
                        #update the new ratio for pricing and slippage 
                        price_before = (apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
                        amm[pair]['Ratio'][i] = amm[pair]['Staked_amount_Long'][i]/amm[pair]['Staked_amount_Short'][i]
                        amm[pair]['Quote_initial'][i]= apy_history[pair][0]*initial_haircut*amm[pair]['Ratio'][i]
                        amm[pair]['apy_history'][i]=apy_history[pair][i]
                        amm[pair]['slippage'][i]=np.nanmean([amm[pair]['slippage'][i],abs(price_before - amm[pair]['Quote_initial'][i])/price_before])
        
                        #calculate Unrealized PnL again 
                        traders[j]['Unrealized_PnL'][i] = calcUnrealized_perp_traders(traders[j],i)
                        traders[j]['Realized_PnL'][i]=traders[j]['Unrealized_PnL'][i]
                        traders[j]['Unrealized_PnL'][i]=0.0
                        traders[j]['days_elapsed'][i]=0# set the elapsed days to 0 if the position has been closed, otherwise will be +1 if position is not closed 
    
                        # Aggregate_Realized_PnL from this traders (non_zero for closed/liquidated positions)
                        # Insurance only collects positive insurance fee when AMM makes money
                        # If trader make money, AMM get 90% and Insurance get 10%, liquidator gets 0% since not liquidated case  
                        if traders[j]['Realized_PnL'][i]<0:
                          insurance['profit'][i] -= (traders[j]['Realized_PnL'][i]*0.10)
                          aggregate_Realized_PnL[pair] -=(traders[j]['Realized_PnL'][i]*0.9)
                          amm[pair]['Realized_PnL'][i]-=traders[j]['Realized_PnL'][i]*0.9
                          pre_usdc_value = amm[pair]['USDC_Balance'][i]
                          amm[pair]['USDC_Balance'][i]-=traders[j]['Realized_PnL'][i]*0.9
                          updateAMM(amm[pair],i)
                          traders[j]['actual_received'][i]=traders[j]['Realized_PnL'][i] #if not liquidated, then traders pays out all loss himself
                        else: # if trader make money, then AMM take all the loss 
                          aggregate_Realized_PnL[pair] -=traders[j]['Realized_PnL'][i]
                          amm[pair]['Realized_PnL'][i]-=traders[j]['Realized_PnL'][i]
                          #if trader's Realized Profit is greater than USDC, then we will sell vAMM's LP tokens and pay for the traders 
                          #in reality, we will sell 1.05 times to leave some buffer, but in simulation, we have no buffer
                          #Realized PnL of AMM (all stakers and vAMM) will be deducted, but only vAMM's token are sold in order to pay the traders 
                          #when other stkaers unstake, they will bear this "realized loss" by paying back lp tokens to vAMM 
                          if traders[j]['Realized_PnL'][i]>amm[pair]['USDC_Balance'][i]:
                              #lose lp tokens and pay out the USDC to traders, no change to USDC balance
                              amm[pair]['Staked_amount_LP_token'][i] -= traders[j]['Realized_PnL'][i]/uniswap_market['LP_Token_Price'][i] 
                              insufficient_trader[pair]+=1
                              amm[pair]['Staked_amount'][i] =virtual_liquidity+ amm[pair]['Staked_amount_LP_token'][i] * uniswap_market['LP_Token_Price'][i]+amm[pair]['USDC_Balance'][i] 
                              amm[pair]['Staked_amount_Long'][i] -= traders[j]['Realized_PnL'][i]*amm[pair]['Ratio'][i]/(1+amm[pair]['Ratio'][i])
                              amm[pair]['Staked_amount_Short'][i] -= traders[j]['Realized_PnL'][i]*1/(1+amm[pair]['Ratio'][i])
                          elif traders[j]['Realized_PnL'][i]<=amm[pair]['USDC_Balance'][i]:
                              pre_usdc_value = amm[pair]['USDC_Balance'][i]
                              amm[pair]['USDC_Balance'][i] -= traders[j]['Realized_PnL'][i]
                              updateAMM(amm[pair],i)
                        #If exit, charge the trading_fee_out
                        traders[j]['exit_lvl'][i]=amm[pair]['Quote_initial'][i]
                        traders[j]['trading_fee_out'][i]=traders[j]['exit_lvl'][i]*0.01*traders[j]['notional'][i-1]*0.01
                        traders[j]['actual_received'][i]=traders[j]['Realized_PnL'][i]
                        #Aggregate the trading_fee_out to AMM and Insurance
                        aggregate_Revenue[pair] += traders[j]['trading_fee_out'][i]*0.75
                        amm[pair]['revenue'][i] += traders[j]['trading_fee_out'][i]*0.75
                        pre_usdc_value = amm[pair]['USDC_Balance'][i]
                        amm[pair]['USDC_Balance'][i] += traders[j]['trading_fee_out'][i]*0.75
                        updateAMM(amm[pair],i)
                        insurance['trading_fee'][i]+=(traders[j]['trading_fee_out'][i]*0.25)
                    #if trader has previous position and also choose to carry on the position 
                    else: 
                        #inherit the position from i-1 to i 
                        #you don't need to inherit the collateral at t, since it has been updated at the beginning
                        traders[j]['currency'][i]=traders[j]['currency'][i-1]
                        traders[j]['collateral'][i]=traders[j]['collateral'][i-1]
                        traders[j]['notional'][i]=traders[j]['notional'][i-1]
                        traders[j]['leverage'][i]=traders[j]['leverage'][i-1]
                        traders[j]['side'][i] = traders[j]['side'][i-1]
                        traders[j]['entry_lvl'][i]=traders[j]['entry_lvl'][i-1]
                        #since we reset trading volume for each trader and each market every 24 hours, and hence no need to inherent from prev days 
                        #traders[j]['cumulative_Trading_Vol_rebased_aave'][i]=traders[j]['cumulative_Trading_Vol_rebased_aave'][i-1]
                        #traders[j]['cumulative_Trading_Vol_rebased_compound'][i]=traders[j]['cumulative_Trading_Vol_rebased_compound'][i-1]
                        #traders[j]['cumulative_Trading_Vol_rebased_binance'][i]=traders[j]['cumulative_Trading_Vol_rebased_binance'][i-1]
                        #traders[j]['cumulative_Trading_Vol_rebased_ftx'][i]=traders[j]['cumulative_Trading_Vol_rebased_ftx'][i-1]
                        #traders[j]['cumulative_Trading_Vol_rebased_dydx'][i]=traders[j]['cumulative_Trading_Vol_rebased_dydx'][i-1]    
            #Then initiate the new position only if there is no existing position (otherwise should terminate first before initiate new on the same pair)
            #This is because we currently don't monitor multiple positions under traders, we don't care if the trades come from the same person      
            else:
                if bool(random.getrandbits(1)):#assume traders would like to add on new position 
                    pair = random.choice(currencies)
                    """variable_factor of L/S ratio"""
                    #then it is likely to pay(long the rate) if the fixed rate is too low
                    traders[j]['side'][i]=random.choices(population=[1,-1],
                               weights=[long_ratio(i), (1-long_ratio(i))])[0]
                    traders[j]['currency'][i]=pair    
                    #check if the notional of the trader is allowed 
                    if np.sign(traders[j]['side'][i]) > 0: 
                        traders[j]['collateral'][i]=np.random.randint(10,1000)
                        traders[j]['leverage'][i]=random.randint(1,10)
                        traders[j]['notional'][i]=traders[j]['collateral'][i]*traders[j]['leverage'][i]
                        while traders[j]['notional'][i]>0.1*(amm[pair]['Staked_amount'][i]+amm[pair]['net_exposure'][i]+amm[pair]['Unrealized_PnL'][i]):
                            rejected[pair] +=1
                            traders[j]['collateral'][i]=np.random.randint(10,1000)
                            traders[j]['leverage'][i]=random.randint(1,10)
                            traders[j]['notional'][i]=traders[j]['collateral'][i]*traders[j]['leverage'][i]
                    else: #if short 
                        traders[j]['collateral'][i]=np.random.randint(10,1000)
                        traders[j]['leverage'][i]=random.randint(1,10)
                        traders[j]['notional'][i]=traders[j]['collateral'][i]*traders[j]['leverage'][i]
                        while traders[j]['notional'][i]>0.1*(amm[pair]['Staked_amount'][i]-amm[pair]['net_exposure'][i]+amm[pair]['Unrealized_PnL'][i]):
                            rejected[pair] +=1
                            traders[j]['collateral'][i]=np.random.randint(10,1000)
                            traders[j]['leverage'][i]=random.randint(1,10)
                            traders[j]['notional'][i]=traders[j]['collateral'][i]*traders[j]['leverage'][i]
        
                    if traders[j]['side'][i] == 1:
                        amm[pair]['Staked_amount_Long'][i]+= traders[j]['notional'][i]
                        amm[pair]['net_exposure'][i] -= traders[j]['notional'][i]
                    elif traders[j]['side'][i] == -1: 
                        amm[pair]['Staked_amount_Short'][i]+= traders[j]['notional'][i]
                        amm[pair]['net_exposure'][i] += traders[j]['notional'][i]
                    if stakers[j]['currency'][i]!=str(0.0):
                        pair_staker = stakers[j]['currency'][i]
                        stakers[j]['Share_Percentage'][i]=stakers[j]['Staked_LP_Token'][i]/amm[pair_staker]['Staked_amount_LP_token'][i]
                    updateTradingVolume_traders(traders[j],i,j)
                    price_before = amm[pair]['Quote_initial'][0]*amm[pair]['Ratio'][i]
                    amm[pair]['Ratio'][i] = (amm[pair]['Staked_amount_Long'][i])/(amm[pair]['Staked_amount_Short'][i])                                        
                    amm[pair]['Quote_initial'][i]=(apy_history[pair][0]*initial_haircut)*amm[pair]['Ratio'][i]
                    amm[pair]['apy_history'][i]=apy_history[pair][i]
                    amm[pair]['slippage'][i]=np.nanmean([amm[pair]['slippage'][i],abs(price_before - amm[pair]['Quote_initial'][i])/price_before])
                    traders[j]['entry_lvl'][i]=amm[pair]['Quote_initial'][i]
                    """variable_fixed_trading_fee"""
                    traders[j]['trading_fee_in'][i]=traders[j]['notional'][i]*traders[j]['entry_lvl'][i]*0.01*0.01#as of 1%
    
                    #record for amm and insurance
                    aggregate_Revenue[pair]+=traders[j]['trading_fee_in'][i]*0.75
                    amm[pair]['revenue'][i]+=traders[j]['trading_fee_in'][i]*0.75
                    pre_usdc_value = amm[pair]['USDC_Balance'][i]
                    amm[pair]['USDC_Balance'][i]+=traders[j]['trading_fee_in'][i]*0.75
                    updateAMM(amm[pair],i)
                    insurance['trading_fee'][i]+=(traders[j]['trading_fee_in'][i]*0.25)                    
                else:
                    pass

        #After loop over 50 investors, aggregate the positions for next day
        # update net_exposure together with TL and TS of AMM
        """Update Unrealized PnL for Vault at the end of the day0"""
        for pair in currencies:
            vault[pair]['Unrealized_PnL'][i] = calcUnrealized_perp(vault[pair],i)
            aggregate_Unrealized_PnL[pair] -= vault[pair]['Unrealized_PnL'][i]
    
        updateVault_summary(i)
        lpPrice_USDC_exUnrealized(i)
        lpPrice_USDC_inUnrealized(i)
    
        """update Unrealized PnL for all investors at tne end of the day such that next day stakers can get correct Undistributed PnL growth"""
        for j in range(0,50):
            if (traders[j]['Realized_PnL'][i]==0.0) & (traders[j]['currency'][i]!=str(0.0)):
                pair = traders[j]['currency'][i]
                if traders[j]['days_elapsed'][i]==0.0:
                    traders[j]['Unrealized_PnL'][i] = traders[j]['side'][i]* traders[j]['notional'][i]*\
                        (amm[pair]['Quote_initial'][i]*0.01-traders[j]['entry_lvl'][i]*0.01)/(amm[pair]['Quote_initial'][i]*0.01)
                else: 
                    traders[j]['Unrealized_PnL'][i] = calcUnrealized_perp_traders(traders[j],i)
                amm[pair]['Unrealized_PnL'][i] -= traders[j]['Unrealized_PnL'][i]
                aggregate_Unrealized_PnL[pair] -= traders[j]['Unrealized_PnL'][i]
            else:
                pass                 
            # update insurance_pool at end of the day 
            insurance['revenue'][i]=insurance['profit'][i]+insurance['liquidation_fee'][i]+insurance['trading_fee'][i]
            insurance['Staked_amount'][i]=insurance['Staked_amount'][i-1]+\
            insurance['revenue'][i]+insurance['withdrawal'][i]
            
        supply = {}
        for pair in currencies:
            supply[pair]=0.0
        for j in range(0,50):
            if stakers[j]['currency'][i]!=0.0:
                pair_staker = stakers[j]['currency'][i]
                supply[pair_staker] += stakers[j]['Staked_LP_Token'][i]
                stakers[j]['Share_Percentage'][i]=stakers[j]['Staked_LP_Token'][i]/amm[pair_staker]['Staked_amount_LP_token'][i]
        
        for pair in currencies:
            amm[pair]['Liquidated_count'][i]=amm[pair]['Liquidated_count'][i-1]+liquidated[pair]       
            amm[pair]['Rejected_count'][i]=amm[pair]['Rejected_count'][i-1]+rejected[pair]
            amm[pair]['insufficient_trader'][i]=amm[pair]['insufficient_trader'][i-1]+insufficient_trader[pair]
            amm[pair]['insufficient_staker'][i]=amm[pair]['insufficient_staker'][i-1]+insufficient_staker[pair]    
            #update for day after looping over all 50 investors 
            amm[pair]['Realized_PnL_growth'][i]=aggregate_Realized_PnL[pair]
            amm[pair]['revenue_growth'][i]=aggregate_Revenue[pair]
            amm[pair]['Unrealized_PnL_growth'][i]=aggregate_Unrealized_PnL[pair]
            amm[pair]['Undistributed_profit_growth'][i]=amm[pair]['revenue_growth'][i]+ amm[pair]['Realized_PnL_growth'][i]+amm[pair]['Unrealized_PnL_growth'][i]
            amm[pair]['vAMM_staked_amount_LP_token'][i]=amm[pair]['Staked_amount_LP_token'][i]-supply[pair]
            amm[pair]['excess_return'][i] = (amm[pair]['revenue'][i]+amm[pair]['Realized_PnL'][i]+amm[pair]['Unrealized_PnL'][i])+\
                (amm[pair]['vAMM_staked_amount_LP_token'][i]-400000)*uniswap_market['LP_Token_Price'][i]
                
        """give out rewards to stakers, traders and vault at the end of the day """
        sum_staking=amm['aave']['Staked_amount_LP_token'][i]+amm['compound']['Staked_amount_LP_token'][i]+amm['binance']['Staked_amount_LP_token'][i]+\
            amm['ftx']['Staked_amount_LP_token'][i]+amm['dydx']['Staked_amount_LP_token'][i]
        sum_trading = amm['aave']['cumulative_Trading_Vol_rebased_agg'][i]+amm['compound']['cumulative_Trading_Vol_rebased_agg'][i]+\
            amm['ftx']['cumulative_Trading_Vol_rebased_agg'][i]+amm['binance']['cumulative_Trading_Vol_rebased_agg'][i]+amm['dydx']['cumulative_Trading_Vol_rebased_agg'][i]
        for pairs in currencies:            
            amm[pairs]['staking_share'][i]=amm[pairs]['Staked_amount_LP_token'][i]/sum_staking
            amm[pairs]['trading_share'][i]=amm[pairs]['cumulative_Trading_Vol_rebased_agg'][i]/sum_trading            
            amm[pairs]['Undistributed_profit_growth'][i]=amm[pairs]['revenue'][i]+amm[pairs]['Realized_PnL_growth'][i]+amm[pairs]['Unrealized_PnL_growth'][i]
            #give rewards to vault (the only trader)
            vault[pairs]['STRP_reward'][i] += amm[pairs]['trading_share'][i]*3651*vault[pairs]['cumulative_Trading_vol'][i]/amm[pairs]['cumulative_Trading_Vol_rebased_agg'][i]
        #give out to stakers and traders
        for j in range(0,50):
            if stakers[j]['currency'][i]!=str(0.0): #if currently unstaked, then staker will get nothing on this day 
                pair_staker = stakers[j]['currency'][i]
                stakers[j]['reward_staker'][i] += amm[pair_staker]['staking_share'][i]*3651*stakers[j]['Share_Percentage'][i]
                traders[j]['reward_trader'][i]= traders[j]['reward_trader'][i-1]
                for pairs in currencies:    
                    traders[j]['reward_trader'][i]+=amm[pairs]['trading_share'][i]*3651*traders[j]['cumulative_Trading_Vol_rebased_'+pairs][i]/amm[pairs]['cumulative_Trading_Vol_rebased_agg'][i]
                traders[j]['reward_staker'][i] = stakers[j]['reward_staker'][i]
                traders[j]['total_reward'][i]=traders[j]['reward_trader'][i]+traders[j]['reward_staker'][i]
                stakers[j]['Undistributed_profit'][i]=amm[pair_staker]['Undistributed_profit_growth'][i]*stakers[j]['Share_Percentage'][i]
                    
        for pair in currencies:    
            vault[pair]['STRP_reward'][i] = (amm[pair]['trading_share'][i]*3651*vault[pair]['cumulative_Trading_vol'][i]/amm[pair]['cumulative_Trading_Vol_rebased_agg'][i])
            vault_summary['STRP_reward'][i] += (amm[pair]['trading_share'][i]*3651*vault[pair]['cumulative_Trading_vol'][i]/amm[pair]['cumulative_Trading_Vol_rebased_agg'][i])
            
            
        for j in range(0,50):
            #investors can choose to sell their STRP rewards or not (assuming 65% of people will just sell STRP and won't can re-stake to Uniswap LP) 
            #in reality people can also choose to stake in DAO, but since this is out of scope of this simulation, so we assume no one stakes in DAO
            """first liquidity providing - liquidity = sqrt(x0*y0) - min where min = 1000
            else: liquidity = min((x0/reserve0*totalsupply), (y0/reserve1*totalsupply)) 
            liquidity injection = same proprotion as of the current reserve"""
            # x0/y0 = reserves 0/reserves1
            # y0 = x0 * (reserves 1/ reserves 0) = x0* proportion 
            # proportion is based on the current reserves, before new staking into liquidity pool 
            proportion = uniswap_market['USDC_Inventory'][i]/uniswap_market['STRP_Inventory'][i]
            #1 is to re-stake, 0 is do nothing and leave rewards on balance and -1 is to sell STRP token and leave 
            STRP_amount_change = traders[j]['total_reward'][i]*random.choices(population=[1,0,-1],weights=[0.2,0.2,0.6])[0] 
            USDC_amount_change = STRP_amount_change * proportion #y0=x0 * proportion 
            if  STRP_amount_change>0:#mint LP tokens for the additional staking of USDC+STRP 
                uniswap_market['STRP_Inventory'][i]+=STRP_amount_change
                uniswap_market['USDC_Inventory'][i]+=USDC_amount_change 
                restake_amount = min(STRP_amount_change/uniswap_market['STRP_Inventory'][i]*uniswap_market['LP_Token_amount'][i],\
                                                          USDC_amount_change/uniswap_market['USDC_Inventory'][i]*uniswap_market['LP_Token_amount'][i])
                uniswap_market['LP_Token_amount'][i]+=restake_amount #lp token minted for restake amount from STRP rewards
                uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
                    /uniswap_market['LP_Token_amount'][i]   
                #save the restaking amount for next day since rewards are received at the end of day (if this day still have restake amount leve, then just top it up )
                stakers[j]['restake_amount'][i]+= restake_amount
                
                stakers[j]['reward_staker'][i]=0#set to zero since all minted to LP tokens 
                traders[j]['reward_staker'][i]=0
                traders[j]['reward_trader'][i]=0
                traders[j]['total_reward'][i]=0
            
            elif STRP_amount_change<0: #sell STRP on uniswap  
                #uniswap LP will get additional STRP by buying STRP from the seller (STRP inventory increase)
                constant =  uniswap_market['STRP_Inventory'][i]* uniswap_market['USDC_Inventory'][i]#constant k before change 
                uniswap_market['STRP_Inventory'][i]-=STRP_amount_change
                uniswap_market['USDC_Inventory'][i] = constant/uniswap_market['STRP_Inventory'][i]#since it is 50/50
                uniswap_market['STRP_Price'][i]=uniswap_market['USDC_Inventory'][i]/uniswap_market['STRP_Inventory'][i]
                uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
                    /uniswap_market['LP_Token_amount'][i]    
                
                stakers[j]['reward_staker'][i]=0#set to zero since all sold out 
                traders[j]['reward_staker'][i]=0
                traders[j]['reward_trader'][i]=0
                traders[j]['total_reward'][i]=0    
            
            """
            proportion = uniswap_market['USDC_Inventory'][i]/uniswap_market['STRP_Inventory'][i]
            #1 is to re-stake, 0 is do nothing and leave rewards on balance and -1 is to sell STRP token and leave 
            USDC_amount_change = STRP_amount_change * proportion #y0=x0 * proportion 
            #assume all INVESTORS of vault will just choose to sell the tokens
            STRP_amount_change = investors[j]['profit_STRP'][i]*-1
            constant =  uniswap_market['STRP_Inventory'][i]* uniswap_market['USDC_Inventory'][i]#constant k before change 
            uniswap_market['STRP_Inventory'][i]-=STRP_amount_change
            uniswap_market['USDC_Inventory'][i] = constant/uniswap_market['STRP_Inventory'][i]#since it is 50/50
            uniswap_market['STRP_Price'][i]=uniswap_market['USDC_Inventory'][i]/uniswap_market['STRP_Inventory'][i]
            uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
                /uniswap_market['LP_Token_amount'][i]    
            #investors[j]['profit_STRP'][i]=0
            """
          
        if i % 30 ==0:
            #every week, release 15m /24/7 + 10m/36/7 STRP tokens, x% to stake and 10% to keep it and 70% to sell and take profit (using x% assumpotion)
            STRP_amount_change = (15000000/24 +10000000/36)*random.choices(population=[1,0,-1],weights=[0.3,0.4,0.4])[0]
            """since I don't treat investors' staking anything different from stakers, we don't need to set up the scenarios for investors staking
               I don't include these additional staking since it doesn't belong to stakers, and will inflate vAMM token balance (for Treasury)"""
        
            if STRP_amount_change>0:#mint LP tokens for the additional staking of USDC+STRP 
                pass
                """    
                uniswap_market['STRP_Inventory'][i]+=STRP_amount_change
                uniswap_market['USDC_Inventory'][i]+=USDC_amount_change 
                restake_amount = min(STRP_amount_change/uniswap_market['STRP_Inventory'][i]*uniswap_market['LP_Token_amount'][i],\
                                                          USDC_amount_change/uniswap_market['USDC_Inventory'][i]*uniswap_market['LP_Token_amount'][i])
                uniswap_market['LP_Token_amount'][i]+=restake_amount
                uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
                    /uniswap_market['LP_Token_amount'][i]   
                """        
            elif STRP_amount_change<0: #sell STRP on uniswap  
                #uniswap LP will get additional STRP by buying STRP from the seller (STRP inventory increase)
                constant =  uniswap_market['STRP_Inventory'][i]* uniswap_market['USDC_Inventory'][i]#constant k before change 
                uniswap_market['STRP_Inventory'][i]-=STRP_amount_change
                uniswap_market['USDC_Inventory'][i] = constant/uniswap_market['STRP_Inventory'][i]#since it is 50/50
                uniswap_market['STRP_Price'][i]=uniswap_market['USDC_Inventory'][i]/uniswap_market['STRP_Inventory'][i]
                uniswap_market['LP_Token_Price'][i]=(uniswap_market['USDC_Inventory'][i]+uniswap_market['STRP_Inventory'][i]*uniswap_market['STRP_Price'][i])\
                    /uniswap_market['LP_Token_amount'][i]    
            #after calculating the rewards, at the end of the month end 
            for j in range(0,50):
                for pairs in currencies:
                    traders[j]['cumulative_Trading_Vol_rebased_'+pairs][i]=0
            #reset cumulative trading volume at the end of month and update dv01
            for pairs in currencies:
                amm[pairs]['dv01']=amm[pairs]['net_exposure'][i]*0.01/(amm[pairs]['Quote_initial'][i]*0.01)
                amm[pairs]['cumulative_Trading_Vol_rebased_agg'][i]=0
                    
        print('day '+str(apy_history.index[i])+' ended')
    for pair in currencies:
        amm_performance['revenue'][n]+=amm[pair]['revenue'][-1]#cumulative
        amm_performance['Realized_PnL'][n]+=amm[pair]['Realized_PnL'][-1]#cumulative
        amm_performance['Unrealized_PnL'][n]+=amm[pair]['Unrealized_PnL'][-1]#co-current
        amm_performance['liquidated_count'][n]+=amm[pair]['Liquidated_count'][-1]#cumulative
        amm_performance['rejected_count'][n]+=amm[pair]['Rejected_count'][-1]#cumulative
        #return of amm comes from revenue, Realized PnL, Unrealized PnL, and vAMM penalty (didn't count the price appreciation of LP token price or STRP price)
        amm_performance['total_return'][n]+= amm[pair]['excess_return'][-1]        
        amm_performance['AMM_ROI'][n]=amm_performance['total_return'][n]/(amm[pair]['Staked_amount_LP_token'][-1]*uniswap_market['LP_Token_Price'][i].mean())/len(apy_history.index)*365
        amm_performance['net_return'][n] = amm_performance['total_return'][n]+(insurance['Staked_amount'][-1]-1000000)
        amm_performance['Strips_ROI'][n] = amm_performance['net_return'][n]/(amm[pair]['Staked_amount_LP_token'][-1]*uniswap_market['LP_Token_Price'][i].mean())/len(apy_history.index)*365
        
    amm_summary = pd.DataFrame(0.0,columns =['revenue','Realized_PnL','Unrealized_PnL',\
                                             'Undistributed_profit_growth','revenue_growth','Realized_PnL_growth','Unrealized_PnL_growth',\
                                                 'staking_profit','staking_profit_USDC','excess_return',\
                                                     'liquidation_count','rejected_count','insufficient_count','slippage','dv01'],index=apy_history.index)
    
    collateral_summary = pd.DataFrame(0.0,columns = ['Staked_amount','STRP_Price','LP_Token_Price','excess_return'],index = apy_history.index)
    collateral_summary['STRP_Price']=uniswap_market['STRP_Price']
    collateral_summary['LP_Token_Price']=uniswap_market['LP_Token_Price']
    
    for pair in currencies:
        amm_summary['revenue']+=amm[pair]['revenue']
        amm_summary['Realized_PnL']+=amm[pair]['Realized_PnL']
        amm_summary['Unrealized_PnL']+=amm[pair]['Unrealized_PnL']
        amm_summary['Undistributed_profit_growth']+=amm[pair]['Undistributed_profit_growth']
        amm_summary['revenue_growth']+=amm[pair]['revenue_growth']
        amm_summary['Realized_PnL_growth']+=amm[pair]['Realized_PnL_growth']
        amm_summary['Unrealized_PnL_growth']+=amm[pair]['Unrealized_PnL_growth']
        amm_summary['staking_profit']+=amm[pair]['vAMM_staked_amount_LP_token']-400000
        amm_summary['staking_profit_USDC']+=(amm[pair]['vAMM_staked_amount_LP_token']-400000)*uniswap_market['LP_Token_Price']
        amm_summary['excess_return']+=amm[pair]['excess_return']
        amm_summary['liquidation_count']+=amm[pair]['Liquidated_count']
        amm_summary['rejected_count']+=amm[pair]['Rejected_count']
        amm_summary['slippage']+=(amm[pair]['slippage']/5)
        amm_summary['insufficient_count']+=(amm[pair]['insufficient_staker']+amm[pair]['insufficient_trader'])
        amm_summary['dv01']+=(amm[pair]['dv01']/5)
        collateral_summary['excess_return']+=amm[pair]['excess_return']
        collateral_summary['Staked_amount']+=amm[pair]['Staked_amount']
        collateral_summary['staking_APY']=3615*collateral_summary['STRP_Price']/collateral_summary['Staked_amount']*365*100
        collateral_summary['trading_APY']=3615*collateral_summary['STRP_Price']/(amm['aave']['cumulative_Trading_Vol_rebased_agg']+\
                                                                                 amm['binance']['cumulative_Trading_Vol_rebased_agg']+\
                                                                                     amm['compound']['cumulative_Trading_Vol_rebased_agg']+\
                                                                                         amm['ftx']['cumulative_Trading_Vol_rebased_agg']+\
                                                                                             amm['dydx']['cumulative_Trading_Vol_rebased_agg'])*365*100
    #Create folder and save all raw files 
    parent_dir = "C:/Users/CZ/Downloads/Strips.finance/Trading_Strategies/Long_Only/dataset"   
    amm_performance.to_excel(parent_dir+'amm_perforamnce.xlsx')
    
    """for each scenario"""
    directory =str(withdraw_fee)+"_"+str(method)
    path = os.path.join(parent_dir,directory)
    os.mkdir(path)
    print("Directory '% s' created" % directory)
    insurance.to_excel(path+'/'+'insurance.xlsx')
    vault_summary.to_excel(path+'/'+'vault_summary.xlsx')
    amm_summary.to_excel(path+'/'+'amm_summary.xlsx')
    #save amm 
    writer = pd.ExcelWriter(path+'/'+'amm.xlsx', engine='openpyxl')
    for df_name,df in amm.items():
        df.to_excel(writer,sheet_name=df_name)
    writer.save()
    del(writer)
    #save trader
    writer = pd.ExcelWriter(path+'/'+'traders.xlsx', engine='openpyxl')
    for df_name,df in traders.items():
        df.to_excel(writer,sheet_name=str(df_name))
    writer.save()
    del(writer)
    #save staker
    writer = pd.ExcelWriter(path+'/'+'stakers.xlsx', engine='openpyxl')
    for df_name,df in stakers.items():
        df.to_excel(writer,sheet_name=str(df_name))
    writer.save()
    #save vault
    writer = pd.ExcelWriter(path+'/'+'vault.xlsx', engine='openpyxl')
    for df_name,df in vault.items():
        df.to_excel(writer,sheet_name=str(df_name))
    writer.save()
    #save investors
    writer = pd.ExcelWriter(path+'/'+'investors.xlsx', engine='openpyxl')
    for df_name,df in investors.items():
        df.to_excel(writer,sheet_name=str(df_name))
    writer.save()
    
