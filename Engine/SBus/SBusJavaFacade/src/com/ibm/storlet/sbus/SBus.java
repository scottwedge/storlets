/*----------------------------------------------------------------------------
 * Copyright IBM Corp. 2015, 2015 All Rights Reserved
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * Limitations under the License.
 * ---------------------------------------------------------------------------
 */


/*============================================================================
 08-Jul-2014    evgenyl     Initial implementation.
 ===========================================================================*/

package com.ibm.storlet.sbus;

import java.io.IOException;
import com.ibm.storlet.sbus.SBusBackend.eLogLevel;

/*----------------------------------------------------------------------------
 * SBus
 * 
 * The front end Java class for SBus functionality.
 * */
public class SBus 
{
    private SBusHandler hServerSideSBus_;
    private SBusBackend SBusBack_;
    
    /*------------------------------------------------------------------------
     * CTOR
     * 
     * Instantiate the SBusBackend object. Start logging
     * */
    public SBus( final String contId ) throws IOException
    {
        SBusBack_ = new SBusBackend();
        SBusBack_.startLogger( eLogLevel.SBUS_LOG_DEBUG, contId );
    }

    /*------------------------------------------------------------------------
     * create
     * 
     * Initialize the server side SBus
     * */
    public void create( final String strPath ) throws IOException 
    {
        hServerSideSBus_ = SBusBack_.createSBus( strPath );
    }

    /*------------------------------------------------------------------------
     * listen
     * 
     * Listen to the SBus. Suspend the executing thread
     * */
    public void listen() throws IOException 
    {
        SBusBack_.listenSBus(hServerSideSBus_);
    }

    /*------------------------------------------------------------------------
     * receive
     * */
    public SBusDatagram receive() throws IOException 
    {
        SBusRawMessage Msg = SBusBack_.receiveRawMessage( hServerSideSBus_ );
        SBusDatagram Dtg = new SBusDatagram( Msg );
        return Dtg;
    }
    
    /*------------------------------------------------------------------------
     * send
     * */
    public void send( final String       strSBusPath,
                      final SBusDatagram Dtg         ) throws IOException 
    {
        
        SBusRawMessage Msg = Dtg.toRawMessage();
        SBusBack_.sendRawMessage(strSBusPath, Msg);
    }

    /*------------------------------------------------------------------------
     * DTOR
     * 
     * Stop logging
     * */
    public void finalize()
    {
        SBusBack_.stopLogger();
    }
}
/*============================== END OF FILE ===============================*/
