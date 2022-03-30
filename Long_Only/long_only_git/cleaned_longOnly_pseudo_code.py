def longOnlyVault(i):
    """step 1 - for all markets, calcuate the 24hr carry = (floating rate - fixed rate%) / 30 *365 (annualized)
    Because in simulation I am using 24 hours (daily) already, it looks like it is instant carry%
    """ 
    for pair in currencies:
         vault[pair]['apy_history'][i] = apy_history[pair][i]
         vault[pair]['instant_carry%'][i]= (apy_history[pair][i]-amm[pair]['Quote_initial'][i]) #instant carry if long or short at the current market level 
         vault[pair]['expected_return'][i]=vault[pair]['instant_carry%'][i]
         #if trader = long, then maxNotional = 0.1* (real TVL+net exposure of AMM + unrealized PnL)
         #if trader = short, then maxNotional = 0.1* (real TVL - net exposure of AMM + unrealized PnL)        
         """step 2 - for each market, if instant carry < 0, skip the market, but if the instant carry>0, 
         then find the maxNotional to long in the market, for which we can retrieve directly from smart contract
         """
         if vault[pair]['expected_return'][i]>0:
             vault[pair]['maxNotional'][i] = 0.1*(amm[pair]['Staked_amount'][i]+amm[pair]['net_exposure'][i]+amm[pair]['Unrealized_PnL'][i])
             vault[pair]['side'][i]=1
             vault_summary['countPositiveCarry'][i]+=1
    """step 3 - for all markets with positive carry, we decide the weight% of cash allocated to each market
    step 3a - get the average 24hr Carry% across all markets with positive carry 
    step 3b - for each market, its vector = e^(carry / average carry)
    step 3c - for each market, weight = vector / sum(vector of each market)
    step 3d - sanity check: weight = 100% across all markets with positive carry, and if 0% across all negative carry (since not included)"""
    for pair in currencies:
        if vault[pair]['expected_return'][i]>0:
            vault_summary['averageCarry%'][i] += vault[pair]['expected_return'][i]/vault_summary['countPositiveCarry'][i] #running average
    for pair in currencies:
        if vault[pair]['expected_return'][i]>0:
            vault[pair]['vector'][i] = math.exp(vault[pair]['expected_return'][i]/vault_summary['averageCarry%'][i])
            vault_summary['vector_sum'][i] += vault[pair]['vector'][i]
    """step 4 - for each markt, there is a target allocation = USDC balance of the vault wallet * weight% calcualted in step 3c"""
    for pair in currencies:
        vault[pair]['weight%'][i] = vault[pair]['vector'][i]/vault_summary['vector_sum'][i]
        vault[pair]['targetAllocation'][i] = vault[pair]['weight%'][i] *vault_summary['Cash_reserves'][i]
    
    """step 5 - for each market, the Rebalance size to trade on is (target allocation - current position)
    step 5a - because we can only long up to the maxNotional allowed by AMM, and hence we will take the minimum value of maxNotional of the market vs. the Rebalance size 
    always take default leverage = 3x
    """
    for pair in currencies:
        """step 5a - for day 0, there is no existing position, then just long based on rebal size, subject to maxNotional"""
        if i == 0:       
            print('daily rebal for pair: '+pair)
            #only trade market with positive carry with leverage = 1x
            if vault[pair]['expected_return'][i]>0: 
                vault[pair]['side'][i]=1
                vault[pair]['notional'][i] = min(vault[pair]['maxNotional'][i],vault[pair]['targetAllocation'][i])
                vault[pair]['collateral'][i] = vault[pair]['notional'][i]/3
                vault[pair]['position'][i] = vault[pair]['notional'][i]
            else:
                #do nothing if carry is not high enough (to leave some buffer)
                vault[pair]['side'][i]=0 
                vault[pair]['notional'][i]=0
                vault[pair]['collateral'][i]=0
                vault[pair]['position'][i]=0
        elif i>0:
            """step 5a - for any day, if there is no existing position, there is no existing position, then just long based on rebal size, subject to maxNotional"""
            if vault[pair]['position'][i-1] == 0.0: 
                vault[pair]['Rebal_size'][i] = vault[pair]['targetAllocation'][i] - vault[pair]['position'][i-1]
            #open new (same as day 0)
                if vault[pair]['expected_return'][i]>0: 
                    vault[pair]['side'][i]=1
                    vault[pair]['notional'][i] = min(vault[pair]['maxNotional'][i],vault[pair]['targetAllocation'][i]) #here targetAllocation == Rebal_size, since vault[pair]['position'][i]==0
                    vault[pair]['collateral'][i] = vault[pair]['notional'][i]/3
                    vault[pair]['position'][i] = vault[pair]['notional'][i]
                else:
                    #do nothing if carry is not high enough (to leave some buffer)
                    vault[pair]['side'][i]=0 
                    vault[pair]['notional'][i]=0
                    vault[pair]['collateral'][i]=0
                    vault[pair]['position'][i]=0
            """step 5b - if there is existing position, then if Rebalance size > 0, it means we want to buy more with (target allocation - current position), subject to maxNotional
            actually step 5a is same as step 5b, just target allocation == rebal size when there is no existing position, everything are the same between open new position vs. add more to existing position
            the only difference in python code is that one need to calcualte average price (add more) and the other doesn't need to (new entry level)
            """
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
                    #average the price 
                    #new average price = (old average price * old position + new position * new price) / (total position)
                    vault[pair]['avg_price'][i]=(vault[pair]['avg_price'][i-1]*vault[pair]['position'][i-1]+vault[pair]['notional'][i]*amm[pair]['Quote_initial'][i])/(vault[pair]['position'][i-1]+vault[pair]['notional'][i])
                    vault[pair]['position'][i]+=vault[pair]['notional'][i]
                    vault[pair]['collateral'][i] += vault[pair]['notional'][i]/3
                #close / reduce the position 
                """step 5c - if there is existing position, then Rebalacne size < 0
                this can be the reason the 24hr carry% < 0, and hence weight = 0%,and hence Rebalance size = 0 - existing position <0, and it will be a full close
                or this can be the case that this marekt's carry is less attractive compared to other markets, and it will be partial close 
                """
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
                   