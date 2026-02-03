import { plcSetupLabeler } from "@skyware/labeler/scripts";
import * as dotenv from 'dotenv';
import * as path from 'path';

// Load env from the python labeler folder where the credentials are
dotenv.config({ path: '/Users/lucas.sales/AntiGravity Projects/redirector/backend/python/bluesky-labeler/.env' });

async function run() {
    const handle = process.env.BLUESKY_HANDLE as string;
    const password = process.env.BLUESKY_PASSWORD as string;
    const renderUrl = "https://diva-labeler.onrender.com"; // Default render URL found in logs

    console.log(`Starting PLC Setup for ${handle}...`);

    try {
        const result = await plcSetupLabeler({
            handle: handle,
            password: password,
            serviceEndpoint: renderUrl,
            // We can specify a key if we want to reused the one I generated, 
            // but the library usually generates one and returns it.
        });

        console.log("\n=== PLC SETUP SUCCESSFUL ===");
        console.log("DID:", result.did);
        console.log("SIGNING KEY (Set this in Render):");
        console.log(result.signingKey);
        console.log("============================\n");
        console.log("You must now add the SIGNING_KEY above to your Render Environment Variables.");

    } catch (error) {
        console.error("PLC Setup Failed:", error);
    }
}

run();
